"""Queue and history state holder."""

from pathlib import Path
from typing import Any

from backend.models import BatchTriageJob, TriageResult, TriageStatus


class QueueService:
    def __init__(self) -> None:
        self.queue: dict[str, BatchTriageJob] = {}
        self.history: list[dict[str, Any]] = []

    def get(self, job_id: str) -> BatchTriageJob | None:
        return self.queue.get(job_id)

    def put(self, job: BatchTriageJob) -> None:
        self.queue[job.id] = job

    def delete(self, job_id: str) -> None:
        self.queue.pop(job_id, None)

    def find_active_by_source_dir(self, source_dir: str) -> BatchTriageJob | None:
        for job in self.queue.values():
            if job.source_dir == source_dir and job.status in (TriageStatus.pending, TriageStatus.ignored):
                return job
        return None

    def append_history(
        self,
        job_id: str,
        result: TriageResult,
        title: str,
        mode: str = "auto",
        confidence: float = 1.0,
        timestamp: str = "Just now",
    ) -> None:
        self.history.insert(0, {
            "job_id": job_id,
            "result": result,
            "title": title,
            "mode": mode,
            "confidence": confidence,
            "timestamp": timestamp,
        })

    def prune_missing_jobs(self, download_dir: Path) -> None:
        stale = [
            job_id for job_id, job in self.queue.items()
            if job.status == TriageStatus.pending and not (download_dir / job.source_dir).exists()
        ]
        for job_id in stale:
            self.delete(job_id)

    def prune_invalid_jobs(self, valid_source_dirs: set[str]) -> None:
        stale = [
            job_id for job_id, job in self.queue.items()
            if job.status == TriageStatus.pending and job.source_dir not in valid_source_dirs
        ]
        for job_id in stale:
            self.delete(job_id)


default_queue_service = QueueService()
