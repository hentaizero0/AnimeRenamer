"""Pure target path planning for preview and execution."""

from dataclasses import dataclass
from pathlib import Path

from backend.config import AppConfig
from backend.domain.constants import SUBTITLE_SUFFIXES
from backend.domain.mode import resolve_link_dir, resolve_mode
from backend.models import BatchTriageJob, FileTriageItem


@dataclass(frozen=True)
class TargetPlan:
    source_file: Path
    target_file: Path
    link_target: Path | None
    relative_name: Path
    target_filename: str
    episode: int | None
    mode: str


def build_video_stems_by_episode(job: BatchTriageJob, download_dir: Path) -> dict[int, list[str]]:
    stems: dict[int, list[str]] = {}
    for item in job.items:
        if item.ignored or not item.is_video or not item.parsed or item.parsed.episode is None:
            continue
        source_file = download_dir / item.relative_path
        if source_file.exists():
            stems.setdefault(item.parsed.episode, []).append(source_file.stem)
    return stems


def effective_episode(job: BatchTriageJob, item: FileTriageItem) -> int | None:
    active_items = [candidate for candidate in job.items if not candidate.ignored]
    if job.override_episode is not None and len(active_items) == 1:
        return job.override_episode
    return item.parsed.episode if item.parsed else None


def compute_target_plan(
    job: BatchTriageJob,
    item: FileTriageItem,
    config: AppConfig,
    video_stems_by_episode: dict[int, list[str]] | None = None,
    mode: str | None = None,
    link_dir: Path | None = None,
) -> TargetPlan:
    effective_mode = mode or resolve_mode(job, config)
    effective_link_dir = resolve_link_dir(job, config, effective_mode) if link_dir is None else link_dir
    download_dir = Path(config.download_dir)
    storage_dir = Path(config.storage_dir)
    source_file = download_dir / item.relative_path
    anime_name = job.effective_title
    season = job.effective_season
    season_str = f"{season:02d}"
    episode = effective_episode(job, item)

    if episode is not None:
        target_filename = _episode_filename(job, item, source_file, season, video_stems_by_episode or {})
        if effective_mode == "auto":
            target_file = source_file.parent / target_filename
            link_target = (
                effective_link_dir / anime_name / target_filename
                if effective_link_dir and (item.is_video or source_file.suffix.lower() in SUBTITLE_SUFFIXES)
                else None
            )
        else:
            target_file = storage_dir / anime_name / f"Season {season_str}" / target_filename
            link_target = (
                effective_link_dir / anime_name / f"Season {season_str}" / target_filename
                if effective_link_dir and (item.is_video or source_file.suffix.lower() in SUBTITLE_SUFFIXES)
                else None
            )
        return TargetPlan(
            source_file=source_file,
            target_file=target_file,
            link_target=link_target,
            relative_name=Path(target_filename),
            target_filename=target_filename,
            episode=episode,
            mode=effective_mode,
        )

    relative_name = _relative_extra_path(job, source_file, download_dir)
    if effective_mode == "auto":
        target_file = source_file
        link_target = effective_link_dir / anime_name / relative_name if effective_link_dir else None
    else:
        target_file = storage_dir / anime_name / f"Season {season_str}" / relative_name
        link_target = None
    return TargetPlan(
        source_file=source_file,
        target_file=target_file,
        link_target=link_target,
        relative_name=relative_name,
        target_filename=relative_name.name,
        episode=None,
        mode=effective_mode,
    )


def _episode_filename(
    job: BatchTriageJob,
    item: FileTriageItem,
    source_file: Path,
    season: int,
    video_stems_by_episode: dict[int, list[str]],
) -> str:
    episode = effective_episode(job, item)
    season_str = f"{season:02d}"
    episode_str = f"{episode:02d}"
    target_stem = f"{job.effective_title} S{season_str}E{episode_str}"
    for video_stem in video_stems_by_episode.get(episode or 0, []):
        if source_file.name.startswith(video_stem):
            return source_file.name.replace(video_stem, target_stem, 1)
    return f"{target_stem}{''.join(source_file.suffixes)}"


def _relative_extra_path(job: BatchTriageJob, source_file: Path, download_dir: Path) -> Path:
    if job.source_dir != ".":
        try:
            return source_file.relative_to(download_dir / job.source_dir)
        except ValueError:
            return Path(source_file.name)
    return Path(source_file.name)
