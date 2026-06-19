"""
parser.py — Anime filename parsing engine for AnimeRenamer v2.

Design goals
------------
- Pure functions only — no file I/O, no global state, no side effects.
- Never raise on ambiguous input; return a low-confidence ParsedAnime instead.
- Python 3.12, full type hints throughout.

Supported filename patterns (non-exhaustive)
--------------------------------------------
[SubsPlease] Dungeon Meshi - 15 (1080p) [ABC123].mkv
[ANi] Re:从零开始的异世界生活 第三季 - 01 [WebRip 1080p AVC AAC][CHT].mp4
[Lilith-Raws] Mushoku Tensei II - 13 (WebRip 1080p HEVC AAC DualAudio).mkv
[Sakurato] Spice and Wolf - 03 [AVC-8bit 1080p AAC][CHS].mp4
[Mikan Project] Tensei Shitara Slime Datta Ken 3rd Season - 02 [WebRip 1080p HEVC AAC].mkv
[YMDR] Kono Subarashii Sekai ni Shukufuku wo! 3 - 01 [1080p] [HEVC].mkv
[极影字幕社] ★04月新番 忘却Battery ... 第02话 GB MP4 1080p.mp4
05.mkv  (bare episode number; accepts optional torrent_name hint)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from backend.models import ParsedAnime

# ---------------------------------------------------------------------------
# Constants / compiled regexes
# ---------------------------------------------------------------------------

# Known video extensions
_VIDEO_EXTS: frozenset[str] = frozenset(
    {"mkv", "mp4", "avi", "mov", "wmv", "flv", "m4v", "ts", "webm"}
)

# Tags that should be stripped from the title / remaining string.
# Order matters: more-specific patterns first.
_JUNK_TAGS: list[re.Pattern[str]] = [p for p in [
    # Resolution / codec quality tags  (grouped in brackets or standalone)
    re.compile(
        r"[\[(]?"
        r"(?:4K|2160p|1080p|720p|576p|480p|360p)"
        r"(?:[^\])\s]*)?"  # optional extra qualifiers like "1080p60"
        r"[\])]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"[\[(]?"
        r"(?:HEVC|AVC|H\.?264|H\.?265|x264|x265|xvid|divx|vp9|av1)"
        r"(?:-\w+)?"  # e.g. AVC-8bit
        r"[\])]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"[\[(]?"
        r"(?:AAC|AC3|DTS|FLAC|MP3|OPUS|EAC3|TrueHD|Atmos)"
        r"(?:\s*\d+\.\d+)?"  # optional channel count e.g. AAC 2.0
        r"[\])]?",
        re.IGNORECASE,
    ),
    re.compile(r"\bDualAudio\b", re.IGNORECASE),
    re.compile(r"\bWebRip\b", re.IGNORECASE),
    re.compile(r"\bBDRip\b", re.IGNORECASE),
    re.compile(r"\bBlu-?Ray\b", re.IGNORECASE),
    re.compile(r"\bHDTV\b", re.IGNORECASE),
    re.compile(r"\bWEB-DL\b", re.IGNORECASE),
    re.compile(r"\b(?:GB|BIG5|BIG5-MP4|MP4|MKV)\b", re.IGNORECASE),
    # Language/subtitle tags
    re.compile(r"\b(?:CHT|CHS|JPN|ENG|MULTI|Sub|Dub)\b", re.IGNORECASE),
    # Hash/CRC tags — [A1B2C3D4]
    re.compile(r"\[[0-9A-Fa-f]{6,8}\]"),
    # Bare parenthetical junk: (v2), (BD), (END), (FINAL)
    re.compile(r"\((?:v\d+|BD|END|FINAL|OVA|ONA|SP)\)", re.IGNORECASE),
    # Standalone brackets with only spaces inside
    re.compile(r"\[\s*\]|\(\s*\)"),
]]

# Chinese month-new-season prefix: ★04月新番  or  ★ 04月新番
_CN_SEASON_PREFIX = re.compile(r"[★*]\s*\d{1,2}月新番\s*", re.UNICODE)

# Fansub group at start: [GroupName] or 【GroupName】
_FANSUB_BRACKET = re.compile(
    r"^(?:\[(?P<sq>[^\]]+)\]|【(?P<dq>[^】]+)】)\s*",
    re.UNICODE,
)

# ---------- Season patterns ----------

# Chinese ordinal seasons: 第一季 第二季 ... 第十季
_CN_SEASON_ORDINALS: dict[str, int] = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_CN_SEASON_RE = re.compile(r"第([一二三四五六七八九十])季", re.UNICODE)

# Roman numerals II–VIII (standalone word, after a space)
_ROMAN_SEASON_RE = re.compile(r"\b(II|III|IV|VI|VII|VIII|IX)\b")
_ROMAN_VALUES: dict[str, int] = {
    "II": 2, "III": 3, "IV": 4, "VI": 6, "VII": 7, "VIII": 8, "IX": 9,
}

# English ordinal: "2nd Season", "3rd Season", "4th Season", etc.
_ORDINAL_SEASON_RE = re.compile(
    r"(\d+)(?:st|nd|rd|th)\s+Season", re.IGNORECASE
)

# Explicit: "Season 2", "S02", "S2"
_EXPLICIT_SEASON_RE = re.compile(
    r"(?:Season\s*(\d+)|S(\d{1,2})(?!E\d))",
    re.IGNORECASE,
)

# Trailing title digit: "KonoSuba 3 - 01" → season 3
# (used only when no other season found and digit precedes separator)
_TRAILING_TITLE_DIGIT_RE = re.compile(
    r"(?<!\d)(\d)\s*(?:-\s*\d|$)"
)

# ---------- Episode patterns ----------

# Dash separator: " - 03" or " - 003"
_EP_DASH_RE = re.compile(r"(?:^|\s)-\s*(\d{1,4})(?!\d)")
# Bracketed episode: [03] or [E03]
_EP_BRACKET_RE = re.compile(r"\[(?:E|EP|Ep)?(\d{1,4})\]", re.IGNORECASE)
# Chinese episode marker: 第02话 第002集
_EP_CN_RE = re.compile(r"第(\d{1,4})[话集]", re.UNICODE)
# E / EP prefix: E03, EP03
_EP_PREFIX_RE = re.compile(r"\bE(?:P)?(\d{1,4})\b", re.IGNORECASE)
# Final fallback: a standalone 2-digit number likely to be episode
_EP_BARE_RE = re.compile(r"(?:^|[\s_-])(\d{2,3})(?=$|[\s_.\-\[(])")

# ---------- Noise cleaning ----------

# Collapse multiple spaces/dashes left after tag removal
_MULTI_SPACE_RE = re.compile(r"\s{2,}")
_LEADING_TRAILING_DASH_RE = re.compile(r"^\s*[-–—]+\s*|\s*[-–—]+\s*$")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class _ParseState:
    """Mutable working state collected during parsing."""

    raw: str
    stem: str = ""           # filename without extension
    ext: str = ""
    fansub_group: str | None = None
    season: int | None = None
    episode: int | None = None
    title_candidate: str = ""
    flags: set[str] = field(default_factory=set)  # debug / confidence flags


def _extract_extension(filename: str) -> tuple[str, str]:
    """Return (stem, ext) where ext has no leading dot."""
    _, dot_ext = os.path.splitext(filename)
    ext = dot_ext.lstrip(".").lower()
    stem = filename[: len(filename) - len(dot_ext)]
    return stem, ext


def _extract_fansub(stem: str) -> tuple[str, str | None]:
    """
    If the stem starts with a bracketed group name, strip it and return
    (remaining_stem, group_name).  Otherwise return (stem, None).
    """
    m = _FANSUB_BRACKET.match(stem)
    if m:
        group = (m.group("sq") or m.group("dq") or "").strip()
        remaining = stem[m.end():]
        return remaining, group or None
    return stem, None


def _extract_season(text: str) -> tuple[str, int | None, list[str]]:
    """
    Scan *text* for season indicators.  Return (cleaned_text, season_num, flags).
    Flags are short strings describing which pattern fired.
    """
    flags: list[str] = []
    season: int | None = None

    # 1. Chinese ordinal season: 第三季
    m = _CN_SEASON_RE.search(text)
    if m:
        season = _CN_SEASON_ORDINALS.get(m.group(1))
        text = text[: m.start()] + text[m.end():]
        flags.append("cn_season")

    # 2. English ordinal: "3rd Season"
    if season is None:
        m = _ORDINAL_SEASON_RE.search(text)
        if m:
            season = int(m.group(1))
            text = text[: m.start()] + text[m.end():]
            flags.append("ordinal_season")

    # 3. Explicit "Season N" or "S02"
    if season is None:
        m = _EXPLICIT_SEASON_RE.search(text)
        if m:
            season = int(m.group(1) or m.group(2))
            text = text[: m.start()] + text[m.end():]
            flags.append("explicit_season")

    # 4. Roman numeral at word boundary
    if season is None:
        m = _ROMAN_SEASON_RE.search(text)
        if m:
            season = _ROMAN_VALUES[m.group(1)]
            text = text[: m.start()] + text[m.end():]
            flags.append("roman_season")

    return text, season, flags


def _extract_episode(text: str) -> tuple[str, int | None, list[str]]:
    """
    Scan *text* for episode indicators.  Return (cleaned_text, episode_num, flags).
    Tries patterns in priority order; stops at first match.
    """
    flags: list[str] = []
    episode: int | None = None

    # 1. Chinese episode marker: 第02话
    m = _EP_CN_RE.search(text)
    if m:
        episode = int(m.group(1))
        text = text[: m.start()] + text[m.end():]
        flags.append("cn_ep")
        return text, episode, flags

    # 2. E/EP prefix: E03 EP03
    m = _EP_PREFIX_RE.search(text)
    if m:
        episode = int(m.group(1))
        text = text[: m.start()] + text[m.end():]
        flags.append("ep_prefix")
        return text, episode, flags

    # 3. Bracketed: [03] [E03]
    m = _EP_BRACKET_RE.search(text)
    if m:
        episode = int(m.group(1))
        text = text[: m.start()] + text[m.end():]
        flags.append("ep_bracket")
        return text, episode, flags

    # 4. Dash-separated: " - 03"
    m = _EP_DASH_RE.search(text)
    if m:
        episode = int(m.group(1))
        text = text[: m.start()] + text[m.end():]
        flags.append("ep_dash")
        return text, episode, flags

    # 5. Fallback: standalone 2-3 digit number
    m = _EP_BARE_RE.search(text)
    if m:
        episode = int(m.group(1))
        text = text[: m.start()] + text[m.end():]
        flags.append("ep_bare")
        return text, episode, flags

    return text, None, flags


def _strip_junk_tags(text: str) -> str:
    """Remove codec, resolution, language, and hash tags from *text*."""
    for pattern in _JUNK_TAGS:
        text = pattern.sub(" ", text)
    return text


def _clean_title(text: str) -> str:
    """
    Final cosmetic cleanup of a title candidate:
    - Remove leftover brackets/parentheses if they are empty or mismatched.
    - Collapse multiple spaces.
    - Strip leading/trailing dashes, spaces.
    """
    # Remove empty brackets
    text = re.sub(r"\[\s*\]|\(\s*\)", "", text)
    # Remove unmatched opening brackets at start
    text = re.sub(r"^\s*[\[({]+\s*", "", text)
    # Remove unmatched closing brackets at end
    text = re.sub(r"\s*[\])}]+\s*$", "", text)
    text = _LEADING_TRAILING_DASH_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def _compute_confidence(
    episode: int | None,
    season: int | None,
    title: str,
    ep_flags: list[str],
    season_flags: list[str],
    ext_known: bool,
) -> float:
    """
    Heuristic confidence score.

    Starts at 0.5 and adjusts based on evidence quality.
    """
    score = 0.5

    # Episode found — significant positive signal
    if episode is not None:
        score += 0.25
        # High-quality episode detection patterns
        if any(f in ep_flags for f in ("cn_ep", "ep_prefix", "ep_bracket", "ep_dash")):
            score += 0.05
        # Bare fallback is weaker
        if "ep_bare" in ep_flags:
            score -= 0.05

    # Season found
    if season is not None:
        score += 0.05

    # Title looks reasonable: non-empty, not just numbers/symbols
    if title and re.search(r"[A-Za-z\u4e00-\u9fff]", title):
        score += 0.10
    else:
        score -= 0.20

    # Known video extension
    if ext_known:
        score += 0.05

    # Title too short is suspicious
    if len(title) < 2:
        score -= 0.30

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_file(filename: str, torrent_name: str | None = None) -> ParsedAnime:
    """
    Parse an anime filename and return a :class:`~backend.models.ParsedAnime`.

    Parameters
    ----------
    filename:
        The bare filename (or full path — the basename is extracted).
    torrent_name:
        Optional torrent name that may provide additional context when the
        filename is a bare episode number like ``05.mkv``.

    Returns
    -------
    ParsedAnime
        Always returns a result.  Confidence will be low (<0.6) when the
        parser cannot confidently identify the title or episode.
    """
    # Work only on the basename
    filename = os.path.basename(filename)
    stem, ext = _extract_extension(filename)
    ext_known = ext in _VIDEO_EXTS

    # --- If bare numeric stem, use torrent_name as the source ---
    if re.fullmatch(r"\d+", stem.strip()):
        source = torrent_name or stem
        episode_from_stem = int(stem.strip()) if re.fullmatch(r"\d+", stem.strip()) else None
        result = _parse_stem(source, ext)
        # Override episode with the numeric stem if it wasn't found in torrent_name
        if episode_from_stem is not None and result.episode is None:
            return ParsedAnime(
                raw_filename=filename,
                detected_title=result.detected_title,
                season=result.season,
                episode=episode_from_stem,
                extension=ext,
                fansub_group=result.fansub_group,
                confidence=min(result.confidence, 0.55),  # bare stem → cap confidence
            )
        return ParsedAnime(
            raw_filename=filename,
            detected_title=result.detected_title,
            season=result.season,
            episode=result.episode if result.episode is not None else episode_from_stem,
            extension=ext,
            fansub_group=result.fansub_group,
            confidence=min(result.confidence, 0.55),
        )

    result = _parse_stem(stem, ext)
    return ParsedAnime(
        raw_filename=filename,
        detected_title=result.detected_title,
        season=result.season,
        episode=result.episode,
        extension=ext,
        fansub_group=result.fansub_group,
        confidence=result.confidence,
    )


# ---------------------------------------------------------------------------
# Internal stem parser
# ---------------------------------------------------------------------------


def _parse_stem(stem: str, ext: str) -> ParsedAnime:  # noqa: C901 (complexity OK here)
    """
    Core parsing logic operating on a filename stem (no extension).
    Returns a ParsedAnime with raw_filename == stem for internal use;
    the caller sets the real raw_filename.
    """
    ext_known = ext in _VIDEO_EXTS
    working = stem

    # 1. Strip Chinese month-new-season prefix (★04月新番)
    working = _CN_SEASON_PREFIX.sub("", working)

    # 2. Extract fansub group
    working, fansub_group = _extract_fansub(working)

    # 3. Extract season (modifies working string)
    working, season, season_flags = _extract_season(working)

    # 4. Extract episode (modifies working string)
    working, episode, ep_flags = _extract_episode(working)

    # 5. Strip codec / resolution / language junk tags
    working = _strip_junk_tags(working)

    # 6. Check for trailing title digit as season fallback
    #    e.g. "KonoSuba 3" after episode stripped
    if season is None:
        m = re.search(r"(?<![0-9A-Za-z])([2-9])\s*$", working.strip())
        if m:
            season = int(m.group(1))
            working = working[: m.start()]
            season_flags.append("trailing_digit")

    # 7. Final title cleanup
    title = _clean_title(working)

    # 8. Compute confidence
    confidence = _compute_confidence(
        episode=episode,
        season=season,
        title=title,
        ep_flags=ep_flags,
        season_flags=season_flags,
        ext_known=ext_known,
    )

    return ParsedAnime(
        raw_filename=stem,
        detected_title=title,
        season=season,
        episode=episode,
        extension=ext,
        fansub_group=fansub_group,
        confidence=confidence,
    )
