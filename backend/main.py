import asyncio
from typing import Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from backend.models import TriageJob, TriageResult, TriageStatus, SeriesConfig
from backend.config import load_config, SeriesDB
from backend.triage import execute_triage_job
from backend.watcher import start_watcher

app = FastAPI(title="AnimeRenamer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = load_config()
series_db = SeriesDB()

# In-memory stores
queue: dict[str, TriageJob] = {}
history: list[TriageResult] = []

watcher_observer = None

@app.on_event("startup")
async def startup_event():
    global watcher_observer
    loop = asyncio.get_running_loop()
    watcher_observer = start_watcher(loop)

@app.on_event("shutdown")
async def shutdown_event():
    if watcher_observer:
        watcher_observer.stop()
        watcher_observer.join()

@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    pending = sum(1 for j in queue.values() if j.status == TriageStatus.pending)
    errors = sum(1 for j in history if not j.success)
    today = len(history)  # Simplified, could filter by date
    return {"pending": pending, "today": today, "errors": errors}

@app.get("/api/queue")
async def get_queue() -> list[TriageJob]:
    return [j for j in queue.values() if j.status == TriageStatus.pending]

@app.post("/api/queue/{job_id}/confirm")
async def confirm_job(job_id: str) -> TriageResult:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = queue[job_id]
    job.status = TriageStatus.confirmed
    
    res = await execute_triage_job(job, config, dry_run=False)
    
    history.insert(0, res)
    if res.success:
        job.status = TriageStatus.done
        del queue[job_id]
    else:
        job.status = TriageStatus.error
        
    return res

@app.post("/api/queue/{job_id}/skip")
async def skip_job(job_id: str) -> dict[str, str]:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = queue[job_id]
    job.status = TriageStatus.skipped
    del queue[job_id]
    return {"status": "skipped"}

@app.patch("/api/queue/{job_id}")
async def patch_job(job_id: str, updates: dict[str, Any]) -> TriageJob:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = queue[job_id]
    if "title" in updates:
        job.override_title = updates["title"]
    if "season" in updates:
        job.override_season = updates["season"]
    if "episode" in updates:
        job.override_episode = updates["episode"]
        
    return job

@app.get("/api/history")
async def get_history() -> list[TriageResult]:
    return history

@app.post("/api/scan")
async def trigger_scan() -> dict[str, str]:
    # Placeholder for watcher integration
    # Ideally triggers a manual scan of the download directory
    return {"status": "scan triggered"}

@app.get("/api/series")
async def get_series() -> dict[str, SeriesConfig]:
    return series_db._series

@app.post("/api/series")
async def add_series(series: SeriesConfig) -> dict[str, str]:
    series_db.add(series)
    return {"status": "added"}

@app.put("/api/series/{name}")
async def update_series(name: str, series: SeriesConfig) -> dict[str, str]:
    series_db.add(series, title=name)
    return {"status": "updated"}

@app.delete("/api/series/{name}")
async def delete_series(name: str) -> dict[str, str]:
    if name in series_db._series:
        del series_db._series[name]
        series_db.save()
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Series not found")
