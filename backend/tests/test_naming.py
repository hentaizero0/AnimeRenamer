from pathlib import Path

from backend.config import AppConfig
from backend.domain.naming import build_video_stems_by_episode, compute_target_plan
from backend.models import BatchTriageJob, FileTriageItem, ParsedAnime, SeriesConfig


def test_compute_target_plan_for_confirm_episode(tmp_path):
    download_dir = tmp_path / "downloads"
    storage_dir = tmp_path / "storage"
    (download_dir / "Show").mkdir(parents=True)
    source = download_dir / "Show" / "01.mkv"
    source.write_text("x")
    config = AppConfig(download_dir=str(download_dir), storage_dir=str(storage_dir), jellyfin_collect_dir=str(tmp_path / "collect"))
    parsed = ParsedAnime(raw_filename="01.mkv", detected_title="Show", season=1, episode=1, extension="mkv", confidence=0.9)
    item = FileTriageItem(relative_path="Show/01.mkv", parsed=parsed, is_video=True)
    job = BatchTriageJob(id="job", source_dir="Show", items=[item], series_config=SeriesConfig(mode="confirm", tmdb_name="Show", season=1))
    plan = compute_target_plan(job, item, config, build_video_stems_by_episode(job, Path(config.download_dir)))
    assert plan.target_file == storage_dir / "Show" / "Season 01" / "Show S01E01.mkv"
    assert plan.link_target == tmp_path / "collect" / "Show" / "Season 01" / "Show S01E01.mkv"


def test_compute_target_plan_for_confirm_extra(tmp_path):
    download_dir = tmp_path / "downloads"
    storage_dir = tmp_path / "storage"
    (download_dir / "Show" / "NCOP").mkdir(parents=True)
    source = download_dir / "Show" / "NCOP" / "creditless.mkv"
    source.write_text("x")
    config = AppConfig(download_dir=str(download_dir), storage_dir=str(storage_dir))
    item = FileTriageItem(relative_path="Show/NCOP/creditless.mkv", parsed=None, is_video=True)
    job = BatchTriageJob(id="job", source_dir="Show", items=[item], default_mode="confirm", override_title="Show")
    plan = compute_target_plan(job, item, config)
    assert plan.target_file == storage_dir / "Show" / "Season 01" / "NCOP" / "creditless.mkv"
    assert plan.link_target is None
