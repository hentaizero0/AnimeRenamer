import asyncio
import time
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend.domain.constants import EXTRA_DIR_KEYWORDS, IGNORED_DIR_NAMES, SUBTITLE_SUFFIXES, VIDEO_SUFFIXES
from backend.domain.mode import resolve_mode
from backend.parser import parse_file, is_likely_anime
from backend.models import BatchTriageJob, FileTriageItem, TriageStatus, SeriesConfig
from backend.config import load_config, SeriesDB
from backend.tmdb import TmdbClient
from backend.services.queue_service import QueueService, default_queue_service

logger = logging.getLogger(__name__)


async def tmdb_async_resolve(job_id: str, search_title: str, dir_name: str, config, queue_service: QueueService | None = None, key_resolver=None):
    queue_state = queue_service or default_queue_service
    api_key = key_resolver() if key_resolver else (config.tmdb_api_key or "")
    if not api_key:
        logger.info("[TMDB] Skipping TMDB resolve for %s: API key is empty", job_id)
        return
        
    logger.info("[TMDB] Resolving %s with title='%s', dir='%s'", job_id, search_title, dir_name)
    client = TmdbClient(api_key)
    
    # Try searching by parsed title first
    results = await client.search_anime(search_title)
    
    # If no good results OR we missed a season match, fallback to directory name (which is often cleaner/localized)
    if dir_name and dir_name != ".":
        needs_fallback = not results or results[0].confidence <= 0.6 or results[0].matched_season is None
        if needs_fallback:
            import re
            clean_dir = dir_name
            if clean_dir.startswith("[") or clean_dir.startswith("【"):
                brackets = re.findall(r'\[([^\]]+)\]|【([^】]+)】', clean_dir)
                if len(brackets) >= 2:
                    clean_dir = brackets[1][0] or brackets[1][1]
            
            fallback_results = await client.search_anime(clean_dir)
            if fallback_results:
                # Use fallback if it's generally better, or if it provides a season match that we lacked
                if fallback_results[0].confidence > (results[0].confidence if results else 0) or \
                   (fallback_results[0].matched_season is not None and (not results or results[0].matched_season is None)):
                    results = fallback_results
                    search_title = f"{search_title} (fallback: {clean_dir})"
            
    if not results:
        logger.info("[TMDB] No results found for '%s'", search_title)
        return
    
    logger.info("[TMDB] Found %s results for '%s', best: %s (confidence: %.2f)", len(results), search_title, results[0].name, results[0].confidence)
        
    best_match = results[0]
    # We only override if confidence is reasonably high
    if best_match.confidence > 0.6:
        job = queue_state.get(job_id)
        if job is not None:
            # Create a virtual SeriesConfig for it
            sc = SeriesConfig(
                mode=job.default_mode or "confirm",
                tmdb_name=best_match.name,
                tmdb_id=best_match.tmdb_id,
                season=best_match.matched_season or 1 # Can be further refined by verifying episodes
            )
            job.series_config = sc
            job.override_title = best_match.name
            logger.info("[TMDB] Resolved '%s' -> '%s'", search_title, best_match.name)

def get_local_config(dir_path: Path) -> dict | None:
    # Try reading configuration from local files:
    for name in ["triage.yaml", "triage.json", ".triage.yaml", ".triage.json"]:
        p = dir_path / name
        if p.exists() and p.is_file():
            try:
                if name.endswith(".json"):
                    import json
                    with open(p, "r", encoding="utf-8") as f:
                        return json.load(f)
                else:
                    import yaml
                    with open(p, "r", encoding="utf-8") as f:
                        return yaml.safe_load(f)
            except Exception as e:
                logger.warning("Error loading local config %s: %s", p, e)
    return None

def is_download_root(dir_path: Path) -> bool:
    return get_local_config(dir_path) is not None

def get_root_mode(dir_path: Path) -> str:
    config_data = get_local_config(dir_path)
    if config_data and isinstance(config_data, dict):
        mode = config_data.get("mode") or config_data.get("default_mode")
        if mode in ["auto", "confirm"]:
            return mode
    return "confirm"

def resolve_anime_dir_and_mode(path: Path, download_dir: Path) -> tuple[Path, str] | None:
    try:
        path = Path(path).resolve()
        download_dir = Path(download_dir).resolve()
        path.relative_to(download_dir)
    except ValueError:
        return None

    if path == download_dir:
        return None

    parts = []
    p = path
    while p != download_dir and p != p.parent:
        parts.insert(0, p)
        p = p.parent
    
    def get_anime_root_from_index(idx: int, mode: str) -> tuple[Path, str] | None:
        if idx < len(parts):
            curr = parts[idx]
            has_direct_media = any(f.is_file() and f.suffix.lower() in VIDEO_SUFFIXES for f in curr.iterdir())
            has_subdirs = any(f.is_dir() for f in curr.iterdir())
            has_season_folders = any(f.is_dir() and "season" in f.name.lower() for f in curr.iterdir())
            
            if not has_direct_media and has_subdirs and not has_season_folders:
                # It's an organizational folder! The real anime root is the next level down.
                if idx + 1 < len(parts):
                    return parts[idx + 1], mode
                else:
                    return None
            return curr, mode
        return None

    # parts[0] is the first folder inside download_dir, parts[-1] is the leaf
    for i, part in enumerate(parts):
        if is_download_root(part):
            return get_anime_root_from_index(i + 1, get_root_mode(part))
    
    if parts:
        return get_anime_root_from_index(0, "confirm")
    return None

def find_all_anime_dirs(download_dir: Path) -> list[tuple[Path, str]]:
    results = []
    download_dir = Path(download_dir).resolve()
    if not download_dir.exists():
        return results

    def traverse(curr: Path, inherited_mode: str | None):
        if not curr.is_dir():
            return

        if curr != download_dir and is_download_root(curr):
            mode = get_root_mode(curr)
        else:
            mode = inherited_mode

        for child in curr.iterdir():
            if not child.is_dir():
                continue
                
            child_name_lower = child.name.lower()
            if "season" in child_name_lower or any(e in child_name_lower for e in EXTRA_DIR_KEYWORDS) or child_name_lower in IGNORED_DIR_NAMES:
                continue
            
            if is_download_root(child):
                traverse(child, mode)
                continue
            
            has_direct_media = any(f.is_file() and f.suffix.lower() in VIDEO_SUFFIXES for f in child.iterdir())
            has_subdirs = any(f.is_dir() for f in child.iterdir())
            
            has_season_folders = any(f.is_dir() and ("season" in f.name.lower() or f.name.lower() in EXTRA_DIR_KEYWORDS) for f in child.iterdir())
            
            if has_direct_media or has_season_folders:
                results.append((child, mode or "confirm"))
                
            if has_subdirs:
                # Always traverse into subdirectories that aren't season/extras, because they might be independent anime dirs (like Bangumi/Dandadan)
                if child.name.lower() not in IGNORED_DIR_NAMES:
                    traverse(child, mode)
        return

    traverse(download_dir, None)
    return results

def process_directory(dir_path: Path, config, series_db, strict: bool = False, default_mode: str = "confirm") -> BatchTriageJob | None:
    # Scan an Anime Directory recursively for all files
    items = []
    download_dir = Path(config.download_dir)
    try:
        rel_dir = str(dir_path.relative_to(download_dir))
    except ValueError:
        return None
        
    files_to_process = []
    for f in dir_path.iterdir():
        if f.is_file():
            files_to_process.append(f)
        elif f.is_dir():
            name_lower = f.name.lower()
            if "season" in name_lower or name_lower in EXTRA_DIR_KEYWORDS:
                files_to_process.extend(f.rglob("*"))
                
    for f in files_to_process:
        if f.is_file():
            is_video = f.suffix.lower() in VIDEO_SUFFIXES
            is_sub = f.suffix.lower() in SUBTITLE_SUFFIXES
            
            if not is_video and not is_sub:
                continue
                
            # Check if this file is an Extra (in a subfolder not named 'Season X')
            parent_name = f.parent.name
            is_extra = f.parent != dir_path and not parent_name.lower().startswith("season")
            
            parsed = None
            if not is_extra:
                parsed = parse_file(f.name)
                # Only keep valid parsings for videos/subs to not pollute confidence
                if not is_likely_anime(parsed) and not is_sub:
                    parsed = None
                    
            items.append(FileTriageItem(
                relative_path=str(f.relative_to(download_dir)),
                parsed=parsed,
                is_video=is_video
            ))
                
    video_count = sum(1 for it in items if it.is_video)
    if not items or video_count == 0:
        return BatchTriageJob(
            id=str(int(time.time() * 1000)),
            source_dir=rel_dir,
            items=items,
            status=TriageStatus.ignored,
            ignore_reason="no_video",
            default_mode=default_mode
        )
        
    job_id = str(int(time.time() * 1000))
    job = BatchTriageJob(
        id=job_id,
        source_dir=rel_dir,
        items=items,
        status=TriageStatus.pending,
        default_mode=default_mode
    )
    
    # Try to find series config
    matched_entry = None
    if job.effective_title:
        matched_entry = series_db.match_entry_by_alias(job.effective_title)
        
    if matched_entry:
        matched_title, s_conf = matched_entry
        job.series_config = s_conf
        job.override_title = matched_title
        
    if strict and job.confidence < 0.85:
        job.status = TriageStatus.ignored
        job.ignore_reason = "low_confidence"
        return job
        
    return job

class DownloadDirHandler(FileSystemEventHandler):
    def __init__(self, config, series_db, loop, queue_service: QueueService | None = None, key_resolver=None, persist_state=None):
        self.config = config
        self.series_db = series_db
        self.loop = loop
        self.processed_dirs = set()
        self.queue_service = queue_service or default_queue_service
        self.key_resolver = key_resolver
        self.persist_state = persist_state

    def process_dir_event(self, dir_path: Path, strict: bool = False):
        download_dir = Path(self.config.download_dir)
        resolved = resolve_anime_dir_and_mode(dir_path, download_dir)
        if not resolved:
            return
            
        anime_dir, default_mode = resolved
        if default_mode == "auto":
            strict = False

        try:
            rel_dir = str(anime_dir.relative_to(download_dir))
        except ValueError:
            return
            
        job = process_directory(anime_dir, self.config, self.series_db, strict=strict, default_mode=default_mode)
        if not job:
            return
            
        existing_job = self.queue_service.find_active_by_source_dir(rel_dir)
                
        if existing_job:
            job.id = existing_job.id # Keep the same ID
            # Preserve user edits and TMDB resolutions across refreshes
            job.series_config = existing_job.series_config
            job.override_title = existing_job.override_title
            job.ignore_reason = existing_job.ignore_reason
            
            # Preserve ignored status of individual files
            existing_ignores = {it.relative_path: it.ignored for it in existing_job.items}
            for it in job.items:
                if it.relative_path in existing_ignores:
                    it.ignored = existing_ignores[it.relative_path]
            
        self.queue_service.put(job)
        
        mode = resolve_mode(job, self.config)
            
        if mode == "auto" and job.status == TriageStatus.pending:
            self.loop.create_task(self._tmdb_then_auto(job))
        elif not job.series_config and job.effective_title:
            try:
                dir_name = Path(job.source_dir).name
                self.loop.create_task(tmdb_async_resolve(job.id, job.effective_title, dir_name, self.config, self.queue_service, self.key_resolver))
            except Exception as e:
                logger.warning("Failed to dispatch TMDB task: %s", e)

    async def _tmdb_then_auto(self, job):
        if not job.series_config and job.effective_title:
            dir_name = Path(job.source_dir).name
            await tmdb_async_resolve(job.id, job.effective_title, dir_name, self.config, self.queue_service, self.key_resolver)

        current_job = self.queue_service.get(job.id) or job
        from backend.triage import execute_triage_job

        res = await execute_triage_job(current_job, self.config)

        self.queue_service.append_history(
            current_job.id,
            res,
            current_job.effective_title,
            mode=resolve_mode(current_job, self.config),
            confidence=current_job.confidence,
        )
        if res.success:
            current_job.status = TriageStatus.done
        else:
            current_job.status = TriageStatus.error
            current_job.error_message = res.error_msg
        if self.persist_state:
            self.persist_state()

    def on_created(self, event):
        if not event.is_directory:
            self.loop.call_soon_threadsafe(self.process_dir_event, Path(event.src_path).parent)
            
    def on_moved(self, event):
        if not event.is_directory:
            self.loop.call_soon_threadsafe(self.process_dir_event, Path(event.dest_path).parent)

def start_watcher(loop: asyncio.AbstractEventLoop, queue_service: QueueService | None = None, key_resolver=None, persist_state=None):
    config = load_config("config/series_config.yaml")
    series_db = SeriesDB("config/series_config.yaml")
    download_dir = Path(config.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    
    event_handler = DownloadDirHandler(config, series_db, loop, queue_service=queue_service, key_resolver=key_resolver, persist_state=persist_state)
    observer = Observer()
    observer.schedule(event_handler, str(download_dir), recursive=True)
    observer.start()
    return observer
