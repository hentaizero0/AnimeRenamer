from pathlib import Path

from backend.models import BatchTriageJob, FileTriageItem, ParsedAnime, TriageResult, TriageStatus
from backend.services.queue_service import QueueService


def _job(job_id: str, source_dir: str, status: TriageStatus = TriageStatus.pending) -> BatchTriageJob:
    parsed = ParsedAnime(raw_filename="x.mkv", detected_title="X", season=1, episode=1, extension="mkv", confidence=0.9)
    item = FileTriageItem(relative_path=f"{source_dir}/x.mkv", parsed=parsed, is_video=True)
    return BatchTriageJob(id=job_id, source_dir=source_dir, items=[item], status=status)


def test_find_active_job_by_source_dir():
    service = QueueService()
    service.put(_job("a", "Show"))
    assert service.find_active_by_source_dir("Show").id == "a"


def test_append_history_keeps_result():
    service = QueueService()
    service.append_history("a", TriageResult(success=True, source_path="/src"), "Show")
    assert service.history[0]["job_id"] == "a"
    assert service.history[0]["result"].success is True


def test_prune_missing_jobs(tmp_path):
    service = QueueService()
    service.put(_job("a", "Missing"))
    present = tmp_path / "Present"
    present.mkdir()
    service.put(_job("b", "Present"))
    service.prune_missing_jobs(Path(tmp_path))
    assert "a" not in service.queue
    assert "b" in service.queue
