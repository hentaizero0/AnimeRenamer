"""Mode resolution helpers."""

from pathlib import Path

from backend.config import AppConfig
from backend.models import BatchTriageJob


def resolve_mode(job: BatchTriageJob, config: AppConfig) -> str:
    if job.series_config and job.series_config.mode:
        mode = job.series_config.mode
    elif job.default_mode:
        mode = job.default_mode
    else:
        mode = config.default_mode
    if mode == "auto" and job.has_conflict:
        return "confirm"
    return mode


def resolve_link_dir(job: BatchTriageJob, config: AppConfig, mode: str | None = None) -> Path | None:
    effective_mode = mode or resolve_mode(job, config)
    if effective_mode == "auto":
        return Path(config.jellyfin_airing_dir) if config.jellyfin_airing_dir else None
    return Path(config.jellyfin_collect_dir) if config.jellyfin_collect_dir else None
