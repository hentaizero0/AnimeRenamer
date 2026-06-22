from backend.domain.constants import EXTRA_DIR_KEYWORDS, SUBTITLE_SUFFIXES, VIDEO_EXTENSIONS, VIDEO_SUFFIXES


def test_video_suffixes_include_rmvb():
    assert "rmvb" in VIDEO_EXTENSIONS
    assert ".rmvb" in VIDEO_SUFFIXES


def test_subtitle_suffixes_include_ssa():
    assert ".ssa" in SUBTITLE_SUFFIXES


def test_extra_keywords_cover_common_special_dirs():
    assert {"ncop", "nced", "ova", "sp"}.issubset(EXTRA_DIR_KEYWORDS)
