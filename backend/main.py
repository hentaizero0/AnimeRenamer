import asyncio
import os
import logging
from typing import Any
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.domain.constants import SUBTITLE_SUFFIXES
from backend.domain.mode import resolve_link_dir, resolve_mode
from backend.domain.naming import build_video_stems_by_episode, compute_target_plan
from backend.models import BatchTriageJob, FileTriageItem, TriageResult, TriageStatus, SeriesConfig
from backend.adapters.state_store import coerce_triage_result, load_history, save_history
from backend.config import load_config, SeriesDB
from backend.services.queue_service import default_queue_service
from backend.tmdb import TmdbClient
from backend.triage import execute_triage_job
from backend.watcher import start_watcher, DownloadDirHandler, find_all_anime_dirs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global watcher_observer
    _load_state()
    key = get_effective_tmdb_key()
    if key:
        os.environ["TMDB_API_KEY"] = key
        logger.info("[STARTUP] Loaded TMDB API key: ****%s", key[-4:])
    else:
        logger.info("[STARTUP] No TMDB API key found in settings")
    logger.info("[STARTUP] config.tmdb_api_key: %s...", config.tmdb_api_key[:20] if config.tmdb_api_key else "EMPTY")
    loop = asyncio.get_running_loop()
    watcher_observer = start_watcher(loop, queue_service=queue_service, key_resolver=get_effective_tmdb_key, persist_state=_save_state)
    try:
        yield
    finally:
        if watcher_observer:
            watcher_observer.stop()
            watcher_observer.join()
        await TmdbClient.aclose_all()


app = FastAPI(title="AnimeRenamer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = load_config("config/series_config.yaml")
series_db = SeriesDB("config/series_config.yaml")
queue_service = default_queue_service

# In-memory stores
queue = queue_service.queue
history = queue_service.history

STATE_FILE = Path("state.json")

def _load_state():
    try:
        queue_service.history[:] = load_history(STATE_FILE)
    except Exception as e:
        logger.warning("[WARN] Failed to load state: %s", e)

def _save_state():
    try:
        save_history(STATE_FILE, history)
    except Exception as e:
        logger.warning("[WARN] Failed to save state: %s", e)

watcher_observer = None

SETTINGS_FILE = Path.home() / ".config" / "anime_renamer" / "settings.json"


def _load_settings() -> dict[str, str]:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception as e:
            logger.warning("[WARN] Failed to load settings: %s", e)
    return {"tmdb_api_key": ""}


def _save_settings(settings: dict[str, str]) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        try:
            os.chmod(SETTINGS_FILE, 0o600)
        except OSError:
            pass
    except Exception as e:
        logger.warning("[WARN] Failed to save settings: %s", e)


def get_effective_tmdb_key() -> str:
    key = (_load_settings().get("tmdb_api_key") or "").strip()
    if key and "*" not in key and key != "${TMDB_API_KEY}":
        return key
    env_key = (os.environ.get("TMDB_API_KEY") or "").strip()
    if env_key and "*" not in env_key and env_key != "${TMDB_API_KEY}":
        return env_key
    return ""

@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    pending = sum(1 for j in queue_service.queue.values() if j.status == TriageStatus.pending)
    errors = sum(1 for j in queue_service.history if not (coerce_triage_result(j.get("result")) or TriageResult(success=False, source_path="")).success)
    processed_today = len(history)  # Simplified, could filter by date
    return {"pending": pending, "today": processed_today, "processed_today": processed_today, "errors": errors}

@app.get("/api/pending")
async def get_queue() -> list[dict[str, Any]]:
    res = []
    for j in queue.values():
        if j.status == TriageStatus.pending:
            mode = resolve_mode(j, config)
            target_path = "TBD"
            final_title = j.effective_title
            t_season = j.effective_season
            
            original_parsed = None
            valid_items = [it.parsed.detected_title for it in j.items if it.parsed and it.parsed.detected_title]
            if valid_items:
                from collections import Counter
                original_parsed = Counter(valid_items).most_common(1)[0][0]
                
            if final_title:
                target_path = str(Path(config.storage_dir) / final_title / f"Season {t_season:02d}")

            source_size = "Unknown"
            src = Path(config.download_dir) / j.source_dir
            if src.exists() and src.is_dir():
                sz = sum(f.stat().st_size for f in src.rglob('*') if f.is_file())
                if sz > 1024**3:
                    source_size = f"{sz / (1024**3):.2f} GB"
                else:
                    source_size = f"{sz / (1024**2):.2f} MB"
            elif src.exists() and src.is_file():
                sz = src.stat().st_size
                if sz > 1024**3:
                    source_size = f"{sz / (1024**3):.2f} GB"
                else:
                    source_size = f"{sz / (1024**2):.2f} MB"
            
            from collections import defaultdict
            video_eps: dict[int, list[dict]] = defaultdict(list)
            for i, it in enumerate(j.items):
                if it.is_video and it.parsed and it.parsed.episode is not None:
                    video_eps[it.parsed.episode].append({"index": i, "name": Path(it.relative_path).name, "ignored": it.ignored})
            
            # Report as conflict if there are 2+ total videos for the same episode
            duplicates = {
                ep: files for ep, files in video_eps.items()
                if len(files) >= 2
            }

            ep_set = sorted(set(
                it.parsed.episode
                for it in j.items
                if it.is_video and it.parsed and it.parsed.episode is not None and not it.ignored
            ))
            
            video_count = len(ep_set)
            has_subs = any(1 for it in j.items if it.parsed and f".{it.parsed.extension}" in SUBTITLE_SUFFIXES and not it.ignored)
            renamed_count = sum(1 for it in j.items if it.parsed and it.parsed.episode is not None and not it.ignored)
            total_count = len(j.items)
            
            res.append({
                "id": j.id,
                "original_filename": j.source_dir,
                "detected_title": final_title or "Unknown",
                "original_parsed_title": original_parsed,
                "season": t_season,
                "video_count": video_count,
                "has_subs": has_subs,
                "episode_set": ep_set,
                "duplicates": duplicates,
                "confidence": j.confidence,
                "mode": mode,
                "target_path": f"{target_path}",
                "status": j.status.value,
                "source_size": f"{renamed_count}/{total_count} items",
                "detected_at": datetime.now(timezone.utc).isoformat()
            })
            
    from collections import defaultdict
    title_season_groups: dict[tuple, list[int]] = defaultdict(list)
    for i, item in enumerate(res):
        key = (item["detected_title"], item["season"])
        title_season_groups[key].append(i)

    for key, indices in title_season_groups.items():
        if len(indices) < 2:
            continue
        for i in range(len(indices)):
            for j_idx in range(i + 1, len(indices)):
                a, b = res[indices[i]], res[indices[j_idx]]
                set_a = set(a.get("episode_set", []))
                set_b = set(b.get("episode_set", []))
                if set_a and set_b and set_a.isdisjoint(set_b):
                    combined = sorted(set_a | set_b)
                    a["merge_suggestion"] = {
                        "merge_with_id": b["id"],
                        "merge_with_filename": b["original_filename"],
                        "combined_episodes": combined,
                    }
                    b["merge_suggestion"] = {
                        "merge_with_id": a["id"],
                        "merge_with_filename": a["original_filename"],
                        "combined_episodes": combined,
                    }
                    
    return res

@app.get("/api/ignored")
async def get_ignored() -> list[dict[str, Any]]:
    res = []
    for j in queue.values():
        if j.status == TriageStatus.ignored:
            original_parsed = None
            valid_items = [it.parsed.detected_title for it in j.items if it.parsed and it.parsed.detected_title]
            if valid_items:
                from collections import Counter
                original_parsed = Counter(valid_items).most_common(1)[0][0]
                
            res.append({
                "id": j.id,
                "original_filename": j.source_dir,
                "detected_title": original_parsed or j.effective_title or "Unknown",
                "reason": j.ignore_reason,
                "confidence": j.confidence,
                "items_count": len(j.items),
                "detected_at": datetime.now(timezone.utc).isoformat()
            })
    return res

@app.post("/api/pending/{job_id}/confirm")
async def confirm_job(job_id: str, payload: dict[str, Any] = None) -> TriageResult:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = queue[job_id]
    
    # ponytail: Apply user edits if provided
    if payload:
        if "title" in payload:
            job.override_title = payload["title"]
        if "season" in payload:
            job.override_season = payload["season"]
    
    # Defer deletion: physically delete ignored items before executing triage
    download_dir = Path(config.download_dir)
    for it in job.items:
        if it.ignored:
            file_path = download_dir / it.relative_path
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.info("[CONFIRM] Deleted ignored file: %s", it.relative_path)
                except Exception as e:
                    logger.warning("[CONFIRM] Error deleting ignored file %s: %s", it.relative_path, e)

    job.status = TriageStatus.confirmed
    
    res = await execute_triage_job(job, config, dry_run=False)
    
    queue_service.append_history(job_id, res, job.effective_title, mode=resolve_mode(job, config), confidence=job.confidence)
    if res.success:
        job.status = TriageStatus.done
        del queue[job_id]
    else:
        job.status = TriageStatus.error
    
    _save_state()
    return res

@app.get("/api/pending/{job_id}/preview")
async def preview_job(job_id: str) -> dict:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = queue[job_id]
    anime_name = job.effective_title
    season = job.effective_season
    season_str = f"{season:02d}"
    storage_dir = Path(config.storage_dir)
    mode = resolve_mode(job, config)
    link_dir = resolve_link_dir(job, config, mode)
    
    renamed = []   # files that will be renamed
    preserved = [] # files that will be kept as-is (extras/bonus)
    video_stems_by_ep = build_video_stems_by_episode(job, Path(config.download_dir))
    for it in job.items:
        if it.ignored:
            continue
        plan = compute_target_plan(job, it, config, video_stems_by_ep, mode, link_dir)
        if plan.episode is not None:
            hardlink_root = plan.link_target.parent.parent.name if plan.link_target and mode != "auto" else (plan.link_target.parent.name if plan.link_target else None)
            hardlink_dir = None
            if plan.link_target:
                hardlink_dir = str(plan.link_target.parent.relative_to(link_dir))
            if mode == "auto":
                dest_dir = str(plan.target_file.parent.relative_to(Path(config.download_dir))).replace("\\", "/")
            else:
                dest_dir = str(plan.target_file.parent.relative_to(storage_dir)).replace("\\", "/")
            renamed.append({
                "old_name": plan.source_file.name,
                "new_name": plan.target_filename,
                "new_path": str(plan.target_file),
                "hardlink_path": str(plan.link_target) if plan.link_target else None,
                "dest_root": storage_dir.name,
                "dest_dir": dest_dir,
                "hardlink_root": hardlink_root,
                "hardlink_dir": hardlink_dir,
                "is_video": it.is_video,
                "episode": plan.episode,
            })
        else:
            dest_dir = f"{anime_name}/Season {season_str}/{plan.relative_name.parent}" if (plan.relative_name.parent and plan.relative_name.parent != Path(".")) else f"{anime_name}/Season {season_str}"
            preserved.append({
                "old_name": str(plan.relative_name),
                "new_path": str(plan.target_file),
                "dest_root": storage_dir.name,
                "dest_dir": dest_dir,
                "is_video": it.is_video,
            })
    
    # Sort renamed by episode number
    renamed.sort(key=lambda x: (x["episode"], x["old_name"]))
    
    return {
        "job_id": job_id,
        "anime_name": anime_name,
        "season": season,
        "renamed": renamed,
        "preserved": preserved,
    }

@app.post("/api/pending/{job_id}/items/{item_index}/toggle_ignore")
async def toggle_ignore_item(job_id: str, item_index: int) -> dict[str, Any]:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
    job = queue[job_id]
    if item_index < 0 or item_index >= len(job.items):
        raise HTTPException(status_code=404, detail="Item not found")
    
    target_item = job.items[item_index]
    new_ignored = not target_item.ignored
    target_item.ignored = new_ignored
    
    # Find all files that share the same base stem as the target video
    if target_item.is_video:
        video_name = Path(target_item.relative_path).name
        video_base = video_name
        for _ in range(len(Path(video_name).suffixes)):
            video_base = Path(video_base).stem
        
        for it in job.items:
            if it is target_item:
                continue
            it_name = Path(it.relative_path).name
            it_base = it_name
            for _ in range(len(Path(it_name).suffixes)):
                it_base = Path(it_base).stem
            if it_base == video_base:
                it.ignored = new_ignored
                
    return {"status": "ok", "ignored": target_item.ignored, "deleted": []}

@app.post("/api/pending/{job_id}/skip")
async def skip_job(job_id: str) -> dict[str, str]:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = queue[job_id]
    job.status = TriageStatus.skipped
    del queue[job_id]
    return {"status": "skipped"}

@app.patch("/api/pending/{job_id}")
async def patch_job(job_id: str, updates: dict[str, Any]) -> BatchTriageJob:
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

@app.get("/api/recent")
async def get_history() -> list[dict[str, Any]]:
    res = []
    # Reverse history to show newest first
    for entry in reversed(history):
        r = coerce_triage_result(entry.get("result"))
        if r is None:
            continue
        res.append({
            "id": entry["job_id"],
            "status": "done" if r.success else "error",
            "filename": Path(r.source_path).name if r.source_path else "Unknown",
            "title": entry.get("title", Path(r.dest_path).stem if r.dest_path else "Unknown"),
            "original_filename": Path(r.source_path).name if r.source_path else "Unknown",
            "renamed_to": Path(r.dest_path).name if r.dest_path else None,
            "hardlink_path": str(r.hardlink_path) if r.hardlink_path else None,
            "error_msg": r.error_msg,
            "mode": entry.get("mode", "auto"),
            "confidence": entry.get("confidence", 1.0),
            "timestamp": entry.get("timestamp", "Just now"),
        })
    return res

@app.get("/api/logs")
async def get_logs(status: str | None = None) -> list[dict[str, Any]]:
    logs = await get_history()
    if status:
        logs = [l for l in logs if l["status"] == status]
    return logs

@app.post("/api/scan")
async def trigger_scan() -> dict[str, str]:
    # Defer deletion: physically delete any ignored files in pending jobs before scan
    download_dir = Path(config.download_dir)
    for job in list(queue.values()):
        if job.status == TriageStatus.pending:
            for it in job.items:
                if it.ignored:
                    file_path = download_dir / it.relative_path
                    if file_path.exists():
                        try:
                            file_path.unlink()
                            logger.info("[SCAN] Deleted ignored file: %s", it.relative_path)
                        except Exception as e:
                            logger.warning("[SCAN] Error deleting ignored file %s: %s", it.relative_path, e)

    handler = DownloadDirHandler(config, series_db, asyncio.get_running_loop(), queue_service=queue_service, key_resolver=get_effective_tmdb_key, persist_state=_save_state)
    
    count = 0
    from backend.watcher import find_all_anime_dirs
    dirs_to_scan = find_all_anime_dirs(download_dir)
            
    # Clean up missing directories from queue
    queue_service.prune_missing_jobs(download_dir)
    valid_source_dirs = {str(d.relative_to(download_dir)) for d, _ in dirs_to_scan}
    queue_service.prune_invalid_jobs(valid_source_dirs)

    for d, mode in dirs_to_scan:
        handler.process_dir_event(d, strict=(mode == "confirm"))
        count += 1
        
    return {"status": f"scan triggered, processed {count} directories"}

@app.get("/api/series")
async def get_series() -> list[dict[str, Any]]:
    # ponytail: convert dict to array with metadata for frontend compatibility
    return [{**{"name": name}, **config.model_dump()} for name, config in series_db._series.items()]

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


from pydantic import BaseModel
from backend.watcher import is_download_root, get_root_mode

class DirectoryModeUpdate(BaseModel):
    mode: str

@app.get("/api/directories")
async def get_directories() -> list[dict[str, Any]]:
    download_dir = Path(config.download_dir)
    res = []
    if download_dir.exists() and download_dir.is_dir():
        for child in download_dir.iterdir():
            if child.is_dir():
                is_root = is_download_root(child)
                mode = get_root_mode(child) if is_root else "confirm"
                has_yaml = (child / "triage.yaml").exists() or (child / ".triage.yaml").exists() or (child / "triage.json").exists()
                
                res.append({
                    "name": child.name,
                    "path": child.name,
                    "is_root": is_root,
                    "mode": mode,
                    "has_yaml": has_yaml
                })
    res.sort(key=lambda x: x["name"])
    return res

@app.post("/api/directories/{folder_name:path}/mode")
async def update_directory_mode(folder_name: str, update: DirectoryModeUpdate) -> dict[str, str]:
    if update.mode not in ["auto", "confirm"]:
        raise HTTPException(status_code=400, detail="Invalid mode")
        
    download_dir = Path(config.download_dir)
    target_dir = (download_dir / folder_name).resolve()
    
    try:
        target_dir.relative_to(download_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
        
    yaml_path = target_dir / "triage.yaml"
    hidden_yaml_path = target_dir / ".triage.yaml"
    json_path = target_dir / "triage.json"
    
    # Delete old ones
    if hidden_yaml_path.exists(): hidden_yaml_path.unlink()
    if json_path.exists(): json_path.unlink()
    
    yaml_path.write_text(f"mode: {update.mode}\n", encoding="utf-8")
    
    # Re-scan this directory
    handler = DownloadDirHandler(config, series_db, asyncio.get_running_loop(), queue_service=queue_service, key_resolver=get_effective_tmdb_key, persist_state=_save_state)
    # If mode is auto, we don't need strict matching. If confirm, we use strict.
    strict = (update.mode == "confirm")
    
    # Clean up any pending jobs for this directory
    keys_to_delete = []
    for job_id, job in list(queue.items()):
        if job.status in [TriageStatus.pending, TriageStatus.ignored]:
            src = download_dir / job.source_dir
            try:
                if target_dir in src.parents or target_dir == src:
                    keys_to_delete.append(job_id)
            except: pass
    for k in keys_to_delete:
        del queue[k]
        
    # Re-evaluate all pending jobs that are under this target directory
    # If the root mode changed, their anime dir or mode might have changed
    # Actually, the simplest is just to trigger a rescan on the target dir
    handler.process_dir_event(target_dir)
        
    # Just let the frontend trigger a global scan if they want, or we can scan children
    for child in target_dir.iterdir():
        if child.is_dir():
            handler.process_dir_event(child, strict=strict)
            
    return {"status": "ok", "mode": update.mode}

@app.get("/api/auto_subscriptions")
async def get_auto_subscriptions():
    from backend.models import TriageStatus
    download_dir = Path(config.download_dir)
    dirs = find_all_anime_dirs(download_dir)
    res = []
    
    conflicted_paths = set()
    for job in queue.values():
        if job.status == TriageStatus.pending and getattr(job, "has_conflict", False):
            conflicted_paths.add(job.source_dir)
            
    for d, mode in dirs:
        if mode == "auto":
            try:
                rel = str(d.relative_to(download_dir))
                if rel in conflicted_paths:
                    continue
                res.append({
                    "name": d.name,
                    "path": rel,
                    "mode": mode
                })
            except: pass
    res.sort(key=lambda x: x["name"])
    return res

@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    key = get_effective_tmdb_key()
    return {"has_key": bool(key), "key_hint": f"****{key[-4:]}" if key else ""}

@app.get("/api/settings/validate")
async def validate_settings() -> dict[str, bool]:
    key = get_effective_tmdb_key()
    if not key:
        return {"has_key": False, "valid": False}
    return {"has_key": True, "valid": await TmdbClient(key).validate_key()}

@app.post("/api/settings")
async def update_settings(payload: dict[str, Any] = Body(...)) -> dict[str, str]:
    settings = _load_settings()
    raw = (payload.get("tmdb_api_key") or "").strip()
    if not raw or raw == "${TMDB_API_KEY}":
        return {"status": "unchanged"}
    if "*" in raw:
        raise HTTPException(status_code=400, detail="masked value rejected")
    settings["tmdb_api_key"] = raw
    _save_settings(settings)
    os.environ["TMDB_API_KEY"] = raw
    return {"status": "settings updated"}

# Mount frontend at root last, so API routes take precedence
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
