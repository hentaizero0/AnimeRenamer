"""
models.py — Pydantic v2 data models for AnimeRenamer v2.

All models are immutable by default (frozen=True on ParsedAnime/TriageResult).
TriageJob is mutable so its status and override fields can be updated in-place.
"""

from __future__ import annotations

from enum import Enum
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


class TriageJob(BaseModel):
    """
    Represents a single file that is queued for (or has completed) renaming.

    The `parsed` field holds the raw parser output.  Override fields allow the
    operator (human or auto-confirm logic) to correct the parsed values before
    the file operation is executed.

    Fields
    ------
    parsed:           Output from the filename parser.
    status:           Current lifecycle state.
    override_title:   Operator-supplied title override.
    override_season:  Operator-supplied season override.
    override_episode: Operator-supplied episode override.
    series_config:    Matched SeriesConfig entry, if any.
    error_message:    Human-readable error string when status == 'error'.
    """

    parsed: ParsedAnime
    status: TriageStatus = Field(default=TriageStatus.pending)
    override_title: str | None = Field(default=None)
    override_season: int | None = Field(default=None, ge=1)
    override_episode: int | None = Field(default=None, ge=0)
    series_config: SeriesConfig | None = Field(default=None)
    error_message: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_error_state(self) -> "TriageJob":
        if self.status == TriageStatus.error and not self.error_message:
            raise ValueError(
                "error_message must be set when status is TriageStatus.error"
            )
        return self

    @property
    def effective_title(self) -> str:
        """Return the override title if set, else the parser-detected title."""
        return self.override_title or self.parsed.detected_title

    @property
    def effective_season(self) -> int | None:
        """Return the override season, else the parser-detected season."""
        return (
            self.override_season
            if self.override_season is not None
            else self.parsed.season
        )

    @property
    def effective_episode(self) -> int | None:
        """Return the override episode, else the parser-detected episode."""
        return (
            self.override_episode
            if self.override_episode is not None
            else self.parsed.episode
        )


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
