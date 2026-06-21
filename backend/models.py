"""
models.py — Pydantic v2 data models for AnimeRenamer v2.

All models are immutable by default (frozen=True on ParsedAnime/TriageResult).
TriageJob is mutable so its status and override fields can be updated in-place.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TriageStatus(str, Enum):
    """Lifecycle states for a single triage task."""

    pending = "pending"
    confirmed = "confirmed"
    skipped = "skipped"
    done = "done"
    error = "error"
    ignored = "ignored"


# ---------------------------------------------------------------------------
# ParsedAnime
# ---------------------------------------------------------------------------


class ParsedAnime(BaseModel):
    """
    Result of parsing a single anime filename.

    Fields
    ------
    raw_filename:   The exact filename string that was parsed.
    detected_title: Best-guess series title (cleaned of tags/groups).
    season:         Season number (None if not detected).
    episode:        Episode number (None if not detected).
    extension:      File extension without leading dot, e.g. mkv.
    fansub_group:   Detected fansub/release group (None if absent).
    confidence:     Float in [0, 1] -- how confident the parser is.
    """

    raw_filename: str = Field(..., description="Original filename string passed to the parser")
    detected_title: str = Field(default="", description="Cleaned series title; may be empty")
    season: int | None = Field(None, ge=1, description="Season number (1-based)")
    episode: int | None = Field(None, ge=0, description="Episode number (0 = specials/OVAs)")
    extension: str = Field("", description="File extension without leading dot")
    fansub_group: str = Field(default="", description="Release/fansub group name")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Parser confidence [0, 1]")

    model_config = {"frozen": True}

    @field_validator("extension", mode="before")
    @classmethod
    def normalise_extension(cls, v: str) -> str:
        return v.lstrip(".").lower() if v else ""

    @field_validator("detected_title", mode="before")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip() if v else ""


# ---------------------------------------------------------------------------
# SeriesConfig
# ---------------------------------------------------------------------------


class SeriesConfig(BaseModel):
    """
    A user-configured series entry, typically stored in a YAML/JSON config file.

    Fields
    ------
    mode:       'auto' -- rename without prompting; 'confirm' -- require user approval.
    tmdb_name:  Canonical series title as it appears on TMDB.
    tmdb_id:    TMDB series ID (integer). Optional — None if not yet resolved.
    season:     Default season number for this entry.
    aliases:    Alternative titles / filename patterns that should match this entry.
    """

    mode: str = Field(
        default="confirm",
        pattern=r"^(auto|confirm)$",
        description="Rename mode: 'auto' or 'confirm'",
    )
    tmdb_name: str = Field(..., description="Canonical TMDB series title")
    tmdb_id: int | None = Field(default=None, ge=1, description="TMDB series ID")
    season: int = Field(1, ge=1, description="Target season number")
    aliases: list[str] = Field(default_factory=list, description="Alternative match strings")

    @field_validator("aliases", mode="before")
    @classmethod
    def deduplicate_aliases(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for alias in v:
            stripped = alias.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                result.append(stripped)
        return result


# ---------------------------------------------------------------------------
# TriageJob
# ---------------------------------------------------------------------------


class FileTriageItem(BaseModel):
    relative_path: str = Field(..., description="Path relative to download_dir")
    parsed: ParsedAnime | None = Field(default=None)
    is_video: bool = Field(default=False)
    ignored: bool = Field(default=False, description="If true, skip renaming and tracking this file")

class BatchTriageJob(BaseModel):
    """
    Represents a batch of files (usually a directory) queued for renaming.
    """

    id: str = Field(..., description="Unique job ID")
    source_dir: str = Field(..., description="Relative directory path (e.g. 'Bangumi/Frieren') or '.'")
    items: list[FileTriageItem] = Field(default_factory=list)
    status: TriageStatus = Field(default=TriageStatus.pending)
    override_title: str | None = Field(default=None)
    override_season: int | None = Field(default=None, ge=1)
    override_episode: int | None = Field(None, description="Manually specified episode (or starting episode)")
    series_config: SeriesConfig | None = Field(default=None)
    error_message: str | None = Field(default=None)
    ignore_reason: str | None = Field(None, description="Reason why this job was ignored")
    default_mode: str | None = Field(default=None, description="Default mode inherited from download root")

    @model_validator(mode="after")
    def _validate_error_state(self) -> "BatchTriageJob":
        if self.status == TriageStatus.error and not self.error_message:
            raise ValueError("error_message must be set when status is error")
        return self

    @property
    def effective_title(self) -> str:
        if self.override_title:
            return self.override_title
        if self.series_config and self.series_config.tmdb_name:
            return self.series_config.tmdb_name
        for it in self.items:
            if it.parsed and it.parsed.detected_title:
                return it.parsed.detected_title
        return Path(self.source_dir).name if self.source_dir != "." else "Unknown"

    @property
    def effective_season(self) -> int:
        if self.override_season is not None:
            return self.override_season
        if self.series_config and self.series_config.season:
            return self.series_config.season
        for it in self.items:
            if it.parsed and it.parsed.season is not None:
                return it.parsed.season
        return 1

    @property
    def confidence(self) -> float:
        confs = [it.parsed.confidence for it in self.items if it.parsed]
        return sum(confs) / len(confs) if confs else 0.0

    @property
    def has_conflict(self) -> bool:
        from collections import defaultdict
        video_eps = defaultdict(int)
        for it in self.items:
            if it.is_video and it.parsed and it.parsed.episode is not None and not it.ignored:
                video_eps[it.parsed.episode] += 1
        return any(count >= 2 for count in video_eps.values())


# ---------------------------------------------------------------------------
# TriageResult
# ---------------------------------------------------------------------------


class TriageResult(BaseModel):
    """
    Final outcome after a triage/rename operation has been executed.

    Fields
    ------
    success:       Whether the operation completed without errors.
    source_path:   Absolute path of the original file.
    dest_path:     Absolute path of the renamed destination file.
    hardlink_path: Absolute path of the hardlink copy (None if not created).
    error_msg:     Error message if operation failed.
    rollback_info: Arbitrary dict of information needed to undo the operation.
    """

    success: bool = Field(..., description="True if the operation succeeded")
    source_path: str = Field(..., description="Absolute path to the source file")
    dest_path: str | None = Field(None, description="Absolute path to the renamed destination")
    hardlink_path: str | None = Field(None, description="Absolute path to the hardlink (if created)")
    error_msg: str | None = Field(None, description="Error message if operation failed")
    rollback_info: dict[str, Any] = Field(
        default_factory=dict,
        description="Data required to roll back this operation",
    )

    model_config = {"frozen": True}
