import asyncio
from typing import Any
from datetime import datetime, timezone
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.models import BatchTriageJob, FileTriageItem, TriageResult, TriageStatus, SeriesConfig
from backend.config import load_config, SeriesDB
from backend.triage import execute_triage_job
from backend.watcher import start_watcher, DownloadDirHandler, find_all_anime_dirs

app = FastAPI(title="AnimeRenamer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = load_config("config/series_config.yaml")
series_db = SeriesDB("config/series_config.yaml")

# In-memory stores
queue: dict[str, BatchTriageJob] = {}
history: list[dict] = []

# ponytail: state persistence
STATE_FILE = Path("state.json")

def _load_state():
    """Load state from JSON file on startup"""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            # Only restore non-pending items (pending jobs are ephemeral)
            global history
            history = data.get("history", [])
        except Exception as e:
            print(f"[WARN] Failed to load state: {e}")

def _save_state():
    """Save state to JSON file after each operation"""
    try:
        STATE_FILE.write_text(json.dumps({
            "history": history[-100:],  # Keep last 100 entries
            "timestamp": str(datetime.now(timezone.utc).isoformat())
        }, default=str, indent=2))
    except Exception as e:
        print(f"[WARN] Failed to save state: {e}")

watcher_observer = None

@app.on_event("startup")
async def startup_event():
    global watcher_observer
    _load_state()
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
    errors = sum(1 for j in history if not j["result"].success)
    processed_today = len(history)  # Simplified, could filter by date
    return {"pending": pending, "processed_today": processed_today, "errors": errors}

@app.get("/api/pending")
async def get_queue() -> list[dict[str, Any]]:
    res = []
    for j in queue.values():
        if j.status == TriageStatus.pending:
            s_conf = j.series_config
            mode = s_conf.mode if s_conf else (j.default_mode or config.default_mode)
            if mode == "auto" and j.has_conflict:
                mode = "confirm"
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
            has_subs = any(1 for it in j.items if it.parsed and it.parsed.extension in ["ass", "srt", "ssa"] and not it.ignored)
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
                    print(f"[CONFIRM] Deleted ignored file: {it.relative_path}")
                except Exception as e:
                    print(f"[CONFIRM] Error deleting ignored file {it.relative_path}: {e}")

    job.status = TriageStatus.confirmed
    
    res = await execute_triage_job(job, config, dry_run=False)
    
    history.insert(0, {
        "job_id": job_id,
        "result": res,
        "title": job.effective_title,
    })
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
    
    download_dir = Path(config.download_dir)
    storage_dir = Path(config.storage_dir)
    
    mode = job.series_config.mode if job.series_config else (job.default_mode or config.default_mode)
    if mode == "auto" and job.has_conflict:
        mode = "confirm"
        
    if mode == "auto":
        link_dir = Path(config.jellyfin_airing_dir) if config.jellyfin_airing_dir else None
    else:
        link_dir = Path(config.jellyfin_collect_dir) if config.jellyfin_collect_dir else None
    
    renamed = []   # files that will be renamed
    preserved = [] # files that will be kept as-is (extras/bonus)
    
    # Pre-calculate video stems for preview accuracy
    from collections import defaultdict
    video_stems_by_ep: dict[int, list[str]] = defaultdict(list)
    for it in job.items:
        if it.ignored: continue
        if it.is_video and it.parsed and it.parsed.episode is not None:
            src = download_dir / it.relative_path
            if src.exists():
                video_stems_by_ep[it.parsed.episode].append(src.stem)

    for it in job.items:
        if it.ignored:
            continue
            
        source_file = download_dir / it.relative_path
        old_name = source_file.name
        
        episode = it.parsed.episode if it.parsed else None
        
        if episode is not None:
            season_str = f"{season:02d}"
            episode_str = f"{episode:02d}"
            target_stem = f"{anime_name} S{season_str}E{episode_str}"
            
            target_filename = None
            for v_stem in video_stems_by_ep.get(episode, []):
                if old_name.startswith(v_stem):
                    target_filename = old_name.replace(v_stem, target_stem, 1)
                    break
                    
            if not target_filename:
                ext = "".join(source_file.suffixes)
                target_filename = f"{target_stem}{ext}"
                
            new_path = str(storage_dir / anime_name / f"Season {season_str}" / target_filename)
            hardlink_path = None
            hardlink_root = None
            hardlink_dir = None
            if link_dir and (it.is_video or source_file.suffix.lower() in [".ass", ".srt", ".ssa"]):
                hardlink_path = str(link_dir / anime_name / f"Season {season_str}" / target_filename)
                hardlink_root = link_dir.name
                hardlink_dir = f"{anime_name}/Season {season_str}"

            renamed.append({
                "old_name": old_name,
                "new_name": target_filename,
                "new_path": new_path,
                "hardlink_path": hardlink_path,
                "dest_root": storage_dir.name,
                "dest_dir": f"{anime_name}/Season {season_str}",
                "hardlink_root": hardlink_root,
                "hardlink_dir": hardlink_dir,
                "is_video": it.is_video,
                "episode": episode,
            })
        else:
            # Extra / bonus — preserved with original name
            if job.source_dir != ".":
                try:
                    rel = source_file.relative_to(download_dir / job.source_dir)
                except ValueError:
                    rel = Path(old_name)
            else:
                rel = Path(old_name)
            
            season_str = f"{season:02d}"
            dest_dir = f"{anime_name}/Season {season_str}/{rel.parent}" if (rel.parent and rel.parent != Path(".")) else f"{anime_name}/Season {season_str}"
            preserved.append({
                "old_name": str(rel),   # preserve subdirectory structure in name
                "new_path": str(storage_dir / anime_name / f"Season {season_str}" / rel),
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
        r = entry["result"]
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
                            print(f"[SCAN] Deleted ignored file: {it.relative_path}")
                        except Exception as e:
                            print(f"[SCAN] Error deleting ignored file {it.relative_path}: {e}")

    handler = DownloadDirHandler(config, series_db, asyncio.get_running_loop())
    
    count = 0
    from backend.watcher import find_all_anime_dirs
    dirs_to_scan = find_all_anime_dirs(download_dir)
            
    # Clean up missing directories from queue
    keys_to_delete = []
    for job_id, job in queue.items():
        if job.status == TriageStatus.pending:
            src = Path(config.download_dir) / job.source_dir
            if not src.exists():
                keys_to_delete.append(job_id)
    for k in keys_to_delete:
        del queue[k]
        
    valid_source_dirs = {str(d.relative_to(download_dir)) for d, _ in dirs_to_scan}
    keys_to_delete_invalid = []
    for job_id, job in queue.items():
        if job.status == TriageStatus.pending:
            if job.source_dir not in valid_source_dirs:
                keys_to_delete_invalid.append(job_id)
    for k in keys_to_delete_invalid:
        del queue[k]

    for d, mode in dirs_to_scan:
        handler.process_dir_event(d, strict=(mode == "confirm"))
        count += 1
        
    return {"status": f"scan triggered, processed {count} directories"}

@app.get("/api/series")
async def get_series() -> list[dict[str, Any]]:
    # ponytail: convert dict to array with metadata for frontend compatibility
    return [{**{"name": name}, **config.model_dump()} for name, config in series_db._series.items()]
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
    if False:  # ponytail: path check done via relative_to above:
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
    handler = DownloadDirHandler(config, series_db, asyncio.get_running_loop())
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

# Mount frontend at root last, so API routes take precedence

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
