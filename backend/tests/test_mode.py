from backend.config import AppConfig
from backend.domain.mode import resolve_link_dir, resolve_mode
from backend.models import BatchTriageJob, FileTriageItem, ParsedAnime, SeriesConfig


def _job(**kwargs) -> BatchTriageJob:
    parsed = ParsedAnime(raw_filename="x.mkv", detected_title="X", season=1, episode=1, extension="mkv", confidence=0.9)
    item = FileTriageItem(relative_path="X/x.mkv", parsed=parsed, is_video=True)
    return BatchTriageJob(id="job", source_dir="X", items=[item], **kwargs)


def test_resolve_mode_conflict_downgrades_auto():
    parsed = ParsedAnime(raw_filename="x.mkv", detected_title="X", season=1, episode=1, extension="mkv", confidence=0.9)
    job = BatchTriageJob(
        id="job",
        source_dir="X",
        items=[
            FileTriageItem(relative_path="X/a.mkv", parsed=parsed, is_video=True),
            FileTriageItem(relative_path="X/b.mkv", parsed=parsed, is_video=True),
        ],
        default_mode="auto",
    )
    config = AppConfig(default_mode="confirm")
    assert resolve_mode(job, config) == "confirm"


def test_resolve_link_dir_matches_mode():
    config = AppConfig(jellyfin_airing_dir="/air", jellyfin_collect_dir="/collect")
    assert str(resolve_link_dir(_job(default_mode="auto"), config)) == "/air"
    assert str(resolve_link_dir(_job(series_config=SeriesConfig(mode="confirm", tmdb_name="X", season=1)), config)) == "/collect"
