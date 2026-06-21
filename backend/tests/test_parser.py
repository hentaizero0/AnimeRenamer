"""
tests/test_parser.py — Unit tests for backend.parser and backend.models.

All tests are pure (no filesystem access).  Run with:

    cd /workspaces/anime_triage
    python -m pytest backend/tests/test_parser.py -v
"""

from __future__ import annotations

import pytest

from backend.models import (
    ParsedAnime,
    SeriesConfig,
    FileTriageItem,
    BatchTriageJob,
    TriageResult,
    TriageStatus,
)
from backend.parser import parse_file


# ===========================================================================
# Helpers
# ===========================================================================


def _parse(filename: str, torrent_name: str | None = None) -> ParsedAnime:
    """Thin wrapper so tests read more naturally."""
    return parse_file(filename, torrent_name=torrent_name)


# ===========================================================================
# 1 — ParsedAnime model tests
# ===========================================================================


class TestParsedAnimeModel:
    def test_extension_normalised(self) -> None:
        p = ParsedAnime(raw_filename="a.mkv", extension="mkv", confidence=0.5)
        assert p.extension == "mkv"

    def test_title_stripped(self) -> None:
        p = ParsedAnime(raw_filename="a.mkv", detected_title="Foo", confidence=0.5)
        assert p.detected_title == "Foo"

    def test_confidence_clamped_high(self) -> None:
        with pytest.raises(Exception):
            ParsedAnime(raw_filename="x.mkv", confidence=1.5)

    def test_confidence_clamped_low(self) -> None:
        with pytest.raises(Exception):
            ParsedAnime(raw_filename="x.mkv", confidence=-0.1)

    def test_frozen(self) -> None:
        p = ParsedAnime(raw_filename="x.mkv", confidence=0.8)
        with pytest.raises(Exception):
            p.confidence = 0.1  # type: ignore[misc]


# ===========================================================================
# 2 — SeriesConfig model tests
# ===========================================================================


class TestSeriesConfigModel:
    def test_valid_auto_mode(self) -> None:
        sc = SeriesConfig(mode="auto", tmdb_name="Dungeon Meshi", tmdb_id=1)
        assert sc.mode == "auto"

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(Exception):
            SeriesConfig(mode="manual", tmdb_name="Foo", tmdb_id=1)

    def test_alias_list(self) -> None:
        sc = SeriesConfig(
            tmdb_name="Mushoku Tensei",
            tmdb_id=12345,
            aliases=["Mushoku Tensei", "Jobless Reincarnation"],
        )
        assert "Mushoku Tensei" in sc.aliases
        assert "Jobless Reincarnation" in sc.aliases

    def test_empty_aliases_allowed(self) -> None:
        sc = SeriesConfig(tmdb_name="Solo", tmdb_id=1)
        assert sc.aliases == []

    def test_tmdb_id_required(self) -> None:
        sc = SeriesConfig(tmdb_name="Test", tmdb_id=99)
        assert sc.tmdb_id == 99


# ===========================================================================
# 3 — TriageJob model tests
# ===========================================================================


class TestTriageJobModel:
    def _make_job(self, **kwargs) -> BatchTriageJob:
        parsed = ParsedAnime(
            raw_filename="foo.mkv",
            detected_title="Foo",
            season=1,
            episode=3,
            confidence=0.9,
        )
        item = FileTriageItem(relative_path="foo.mkv", parsed=parsed, is_video=True)
        return BatchTriageJob(id="test-job-1", source_dir=".", items=[item], **kwargs)

    def test_default_status_pending(self) -> None:
        job = self._make_job()
        assert job.status == TriageStatus.pending

    def test_effective_title_falls_back(self) -> None:
        job = self._make_job()
        assert job.effective_title == "Foo"

    def test_effective_title_override(self) -> None:
        job = self._make_job(override_title="Bar")
        assert job.effective_title == "Bar"

    def test_effective_season_override(self) -> None:
        job = self._make_job(override_season=3)
        assert job.effective_season == 3

    def test_effective_episode_override(self) -> None:
        job = self._make_job(override_episode=99)
        assert job.override_episode == 99

    def test_error_status_requires_message(self) -> None:
        with pytest.raises(Exception):
            self._make_job(status=TriageStatus.error)

    def test_error_status_with_message(self) -> None:
        job = self._make_job(
            status=TriageStatus.error, error_message="File not found"
        )
        assert job.status == TriageStatus.error
        assert "not found" in job.error_message


# ===========================================================================
# 4 — TriageResult model tests
# ===========================================================================


class TestTriageResultModel:
    def test_basic_fields(self) -> None:
        r = TriageResult(
            success=True,
            source_path="/src/foo.mkv",
            dest_path="/dest/foo.mkv",
        )
        assert r.hardlink_path is None
        assert r.rollback_info == {}

    def test_frozen(self) -> None:
        r = TriageResult(
            success=True, source_path="/s", dest_path="/d"
        )
        with pytest.raises(Exception):
            r.success = False  # type: ignore[misc]


# ===========================================================================
# 5 — Parser: SubsPlease format
# ===========================================================================


class TestParserSubsPlease:
    """[SubsPlease] Dungeon Meshi - 15 (1080p) [ABC123].mkv"""

    _FILE = "[SubsPlease] Dungeon Meshi - 15 (1080p) [ABC123].mkv"

    def test_group(self) -> None:
        assert _parse(self._FILE).fansub_group == "SubsPlease"

    def test_title(self) -> None:
        assert _parse(self._FILE).detected_title == "Dungeon Meshi"

    def test_episode(self) -> None:
        assert _parse(self._FILE).episode == 15

    def test_extension(self) -> None:
        assert _parse(self._FILE).extension == "mkv"

    def test_season_default_none(self) -> None:
        assert _parse(self._FILE).season is None

    def test_high_confidence(self) -> None:
        assert _parse(self._FILE).confidence >= 0.6


# ===========================================================================
# 6 — Parser: ANi / CJK title format
# ===========================================================================


class TestParserANiCJK:
    """[ANi] Re:从零开始的异世界生活 第三季 - 01 [WebRip 1080p AVC AAC][CHT].mp4"""

    _FILE = "[ANi] Re:从零开始的异世界生活 第三季 - 01 [WebRip 1080p AVC AAC][CHT].mp4"

    def test_group(self) -> None:
        assert _parse(self._FILE).fansub_group == "ANi"

    def test_season_three(self) -> None:
        assert _parse(self._FILE).season == 3

    def test_episode_one(self) -> None:
        assert _parse(self._FILE).episode == 1

    def test_extension(self) -> None:
        assert _parse(self._FILE).extension == "mp4"

    def test_title_stripped_of_cjk_season(self) -> None:
        title = _parse(self._FILE).detected_title
        # Season marker should not appear in title
        assert "第三季" not in title

    def test_title_stripped_of_tags(self) -> None:
        title = _parse(self._FILE).detected_title
        assert "WebRip" not in title
        assert "1080p" not in title


# ===========================================================================
# 7 — Parser: Lilith-Raws / Roman numeral season
# ===========================================================================


class TestParserLilithRaws:
    """[Lilith-Raws] Mushoku Tensei II - 13 (WebRip 1080p HEVC AAC DualAudio).mkv"""

    _FILE = "[Lilith-Raws] Mushoku Tensei II - 13 (WebRip 1080p HEVC AAC DualAudio).mkv"

    def test_group(self) -> None:
        assert _parse(self._FILE).fansub_group == "Lilith-Raws"

    def test_season_roman_ii(self) -> None:
        assert _parse(self._FILE).season == 2

    def test_episode(self) -> None:
        assert _parse(self._FILE).episode == 13

    def test_title_no_roman(self) -> None:
        title = _parse(self._FILE).detected_title
        assert title == "Mushoku Tensei"

    def test_extension(self) -> None:
        assert _parse(self._FILE).extension == "mkv"

    def test_confidence(self) -> None:
        assert _parse(self._FILE).confidence >= 0.6


# ===========================================================================
# 8 — Parser: CJK full-width bracket / ★ new-season tag
# ===========================================================================


class TestParserCJKFullWidth:
    """【极影字幕社】★04月新番 忘却Battery Boukyaku Battery 第02话 GB MP4 1080p.mp4"""

    _FILE = "【极影字幕社】★04月新番 忘却Battery Boukyaku Battery 第02话 GB MP4 1080p.mp4"

    def test_group_extracted(self) -> None:
        assert _parse(self._FILE).fansub_group == "极影字幕社"

    def test_new_season_tag_stripped(self) -> None:
        title = _parse(self._FILE).detected_title
        assert "★" not in title
        assert "月新番" not in title

    def test_episode_cjk(self) -> None:
        assert _parse(self._FILE).episode == 2

    def test_extension(self) -> None:
        assert _parse(self._FILE).extension == "mp4"

    def test_title_contains_series_name(self) -> None:
        title = _parse(self._FILE).detected_title
        assert "Battery" in title

    def test_title_no_resolution_tags(self) -> None:
        title = _parse(self._FILE).detected_title
        assert "1080p" not in title


# ===========================================================================
# 9 — Parser: Sakurato
# ===========================================================================


class TestParserSakurato:
    """[Sakurato] Spice and Wolf - 03 [AVC-8bit 1080p AAC][CHS].mp4"""

    _FILE = "[Sakurato] Spice and Wolf - 03 [AVC-8bit 1080p AAC][CHS].mp4"

    def test_group(self) -> None:
        assert _parse(self._FILE).fansub_group == "Sakurato"

    def test_title(self) -> None:
        assert _parse(self._FILE).detected_title == "Spice and Wolf"

    def test_episode(self) -> None:
        assert _parse(self._FILE).episode == 3

    def test_no_season(self) -> None:
        assert _parse(self._FILE).season is None

    def test_extension(self) -> None:
        assert _parse(self._FILE).extension == "mp4"


# ===========================================================================
# 10 — Parser: Mikan Project / "3rd Season"
# ===========================================================================


class TestParserMikanProject:
    """[Mikan Project] Tensei Shitara Slime Datta Ken 3rd Season - 02 [WebRip 1080p HEVC AAC].mkv"""

    _FILE = "[Mikan Project] Tensei Shitara Slime Datta Ken 3rd Season - 02 [WebRip 1080p HEVC AAC].mkv"

    def test_group(self) -> None:
        assert _parse(self._FILE).fansub_group == "Mikan Project"

    def test_season_ordinal(self) -> None:
        assert _parse(self._FILE).season == 3

    def test_episode(self) -> None:
        assert _parse(self._FILE).episode == 2

    def test_title_no_season_marker(self) -> None:
        title = _parse(self._FILE).detected_title
        assert "3rd Season" not in title
        assert "Season" not in title

    def test_confidence(self) -> None:
        assert _parse(self._FILE).confidence >= 0.6


# ===========================================================================
# 11 — Parser: YMDR / trailing digit season
# ===========================================================================


class TestParserYMDR:
    """[YMDR] Kono Subarashii Sekai ni Shukufuku wo! 3 - 01 [1080p] [HEVC].mkv"""

    _FILE = "[YMDR] Kono Subarashii Sekai ni Shukufuku wo! 3 - 01 [1080p] [HEVC].mkv"

    def test_group(self) -> None:
        assert _parse(self._FILE).fansub_group == "YMDR"

    def test_season_trailing_digit(self) -> None:
        assert _parse(self._FILE).season == 3

    def test_episode(self) -> None:
        assert _parse(self._FILE).episode == 1

    def test_title_cleaned(self) -> None:
        title = _parse(self._FILE).detected_title
        assert "1080p" not in title
        assert "HEVC" not in title

    def test_confidence(self) -> None:
        assert _parse(self._FILE).confidence >= 0.6


# ===========================================================================
# 12 — Parser: Plain episode number file
# ===========================================================================


class TestParserPlainEpisode:
    """05.mkv — minimal filename."""

    def test_no_group(self) -> None:
        r = _parse("05.mkv")
        assert r.fansub_group == ""

    def test_low_confidence_without_hint(self) -> None:
        r = _parse("05.mkv")
        assert r.confidence < 0.6

    def test_extension(self) -> None:
        assert _parse("05.mkv").extension == "mkv"

    def test_returns_parsed_anime(self) -> None:
        """Must return a ParsedAnime without raising."""
        r = _parse("05.mkv")
        assert isinstance(r, ParsedAnime)

    def test_torrent_hint_improves_title(self) -> None:
        r = _parse("05.mkv", torrent_name="[SubsPlease] Dungeon Meshi (01-24)")
        assert "Dungeon Meshi" in r.detected_title

    def test_torrent_hint_group(self) -> None:
        r = _parse("05.mkv", torrent_name="[SubsPlease] Dungeon Meshi (01-24)")
        assert r.fansub_group == "SubsPlease"


# ===========================================================================
# 13 — Parser: edge cases & robustness
# ===========================================================================


class TestParserEdgeCases:
    def test_no_crash_on_minimal_content(self) -> None:
        """A filename that strips to almost nothing should not crash."""
        r = _parse("[Group] - 01 [1080p].mkv")
        assert isinstance(r, ParsedAnime)

    def test_never_raises_on_garbage_input(self) -> None:
        r = _parse("???!!###.mkv")
        assert isinstance(r, ParsedAnime)

    def test_s02_style(self) -> None:
        """Filenames with S02 season marker."""
        r = _parse("[Group] ShowName S02 - 05 [1080p].mkv")
        assert r.season == 2
        assert r.episode == 5

    def test_ep_prefix(self) -> None:
        r = _parse("[Group] ShowName EP07 [1080p].mkv")
        assert r.episode == 7

    def test_e_prefix(self) -> None:
        r = _parse("[Group] ShowName E04 [1080p].mkv")
        assert r.episode == 4

    def test_directory_component_stripped(self) -> None:
        r = _parse("/some/path/[SubsPlease] Dungeon Meshi - 15 (1080p) [ABC123].mkv")
        assert r.detected_title == "Dungeon Meshi"
        assert r.episode == 15

    def test_raw_filename_preserved(self) -> None:
        fname = "[SubsPlease] Dungeon Meshi - 15 (1080p) [ABC123].mkv"
        r = _parse(fname)
        assert r.raw_filename == fname

    def test_confidence_bounded(self) -> None:
        r = _parse("[SubsPlease] Dungeon Meshi - 15 (1080p) [ABC123].mkv")
        assert 0.0 <= r.confidence <= 1.0

    def test_season_word_format(self) -> None:
        r = _parse("[Group] ShowName Season 2 - 01 [1080p].mkv")
        assert r.season == 2

    def test_roman_iii(self) -> None:
        r = _parse("[Group] Overlord III - 01 [1080p].mkv")
        assert r.season == 3

    def test_roman_iv(self) -> None:
        r = _parse("[Group] Overlord IV - 01 [1080p].mkv")
        assert r.season == 4
