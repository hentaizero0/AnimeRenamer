"""Shared file and directory constants."""

VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {"mkv", "mp4", "avi", "mov", "wmv", "flv", "m4v", "ts", "webm", "rmvb"}
)

VIDEO_SUFFIXES: frozenset[str] = frozenset(f".{ext}" for ext in VIDEO_EXTENSIONS)

SUBTITLE_SUFFIXES: frozenset[str] = frozenset({".ass", ".srt", ".ssa"})

EXTRA_DIR_KEYWORDS: frozenset[str] = frozenset(
    {"sp", "bonus", "extras", "nced", "ncop", "menu", "featurettes", "ova", "oad", "scans", "pv", "op", "ed"}
)

IGNORED_DIR_NAMES: frozenset[str] = frozenset({"autolinklog", "logs", "log"})
