import asyncio
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend.parser import parse_file
from backend.models import TriageJob, TriageStatus
from backend.config import load_config, SeriesDB
from backend.triage import execute_triage_job

# We will need access to the queue from main.py
# Using a callback or passing the dict is better, but since it's an isolated module:
import backend.main as main_api

class DownloadDirHandler(FileSystemEventHandler):
    def __init__(self, config, series_db, loop):
        self.config = config
        self.series_db = series_db
        self.loop = loop
        self.processed = set()

    def process_file(self, path: Path):
        # Prevent multiple triggers for the same file in short succession
        if path in self.processed:
            return
        self.processed.add(path)
        
        # We can wait a bit for file to be fully downloaded.
        # But this is a basic implementation.
        time.sleep(2)
        
        try:
            parsed = parse_file(str(path.name))
            
            # Lookup in SeriesDB
            s_conf = None
            if parsed.detected_title:
                s_conf = self.series_db.match_by_alias(parsed.detected_title)
            
            job = TriageJob(
                id=str(int(time.time() * 1000)),
                parsed=parsed,
                status=TriageStatus.pending
            )
            
            # Add to queue
            main_api.queue[job.id] = job
            
            # If auto, execute it immediately
            if s_conf and s_conf.mode == "auto":
                job.title_override = s_conf.tmdb_name
                job.season_override = parsed.season or s_conf.season
                # Execute in event loop
                asyncio.run_coroutine_threadsafe(
                    self._auto_execute(job.id),
                    self.loop
                )
        except Exception as e:
            print(f"Error processing {path}: {e}")

    async def _auto_execute(self, job_id: str):
        # Call confirm_job which handles execution and queue management
        try:
            await main_api.confirm_job(job_id)
        except Exception as e:
            print(f"Auto-execute failed for {job_id}: {e}")

    def on_created(self, event):
        if not event.is_directory:
            self.process_file(Path(event.src_path))
            
    def on_moved(self, event):
        if not event.is_directory:
            self.process_file(Path(event.dest_path))

def start_watcher(loop: asyncio.AbstractEventLoop):
    config = load_config()
    series_db = SeriesDB()
    
    # Ensure directory exists
    download_dir = Path(config.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    
    event_handler = DownloadDirHandler(config, series_db, loop)
    observer = Observer()
    observer.schedule(event_handler, str(download_dir), recursive=False)
    observer.start()
    return observer
