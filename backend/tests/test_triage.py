import pytest
from pathlib import Path
from backend.triage import build_target_path, rename_and_move, create_hardlink, rollback


class TestBuildTargetPath:
    def test_format(self):
        result = build_target_path("无职转生", 2, 13, "mkv", Path("/anime"))
        assert result == Path("/anime/无职转生/Season 2/无职转生 S02E13.mkv")

    def test_season_zero_padding(self):
        result = build_target_path("TestAnime", 1, 5, "mkv", Path("/anime"))
        assert "S01E05" in result.name

    def test_episode_zero_padding(self):
        result = build_target_path("TestAnime", 1, 1, "mkv", Path("/anime"))
        assert "S01E01" in result.name


class TestRenameAndMove:
    def test_dry_run_always_succeeds(self, tmp_path):
        src = tmp_path / "nonexistent.mkv"
        dst = tmp_path / "subdir" / "target.mkv"
        res = rename_and_move(src, dst, dry_run=True)
        assert res.success is True

    def test_moves_file(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dst = tmp_path / "sub" / "dest.mkv"
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is True
        assert dst.exists()
        assert not src.exists()

    def test_creates_parent_dirs(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dst = tmp_path / "a" / "b" / "c" / "dest.mkv"
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is True
        assert dst.exists()

    def test_refuses_existing_target(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dst = tmp_path / "dest.mkv"
        dst.write_text("existing")
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is False
        assert src.exists()

    def test_missing_source_fails(self, tmp_path):
        src = tmp_path / "nonexistent.mkv"
        dst = tmp_path / "dest.mkv"
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is False


class TestCreateHardlink:
    def test_creates_hardlink(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        link = tmp_path / "sub" / "link.mkv"
        res = create_hardlink(src, link, dry_run=False)
        assert res.success is True
        assert link.exists()
        assert src.stat().st_ino == link.stat().st_ino

    def test_dry_run_succeeds(self, tmp_path):
        src = tmp_path / "source.mkv"
        link = tmp_path / "link.mkv"
        res = create_hardlink(src, link, dry_run=True)
        assert res.success is True

    def test_refuses_overwrite_different_file(self, tmp_path):
        src = tmp_path / "a.mkv"
        src.write_text("data A")
        other = tmp_path / "b.mkv"
        other.write_text("data B")
        res = create_hardlink(src, other, dry_run=False)
        assert res.success is False
        assert src.exists()
        assert other.exists()

    def test_idempotent_same_inode(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        link = tmp_path / "link.mkv"
        create_hardlink(src, link, dry_run=False)
        res = create_hardlink(src, link, dry_run=False)
        assert res.success is True


class TestRollback:
    def test_rollback_move(self, tmp_path):
        src = tmp_path / "original.mkv"
        src.write_text("data")
        dst = tmp_path / "moved.mkv"
        mv_res = rename_and_move(src, dst, dry_run=False)
        assert dst.exists()
        ok = rollback(mv_res)
        assert ok is True
        assert src.exists()
        assert not dst.exists()

    def test_rollback_link(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        link = tmp_path / "link.mkv"
        link_res = create_hardlink(src, link, dry_run=False)
        assert link.exists()
        ok = rollback(link_res)
        assert ok is True
        assert not link.exists()
        assert src.exists()

    def test_rollback_empty_info_is_noop(self):
        from backend.models import TriageResult
        r = TriageResult(success=True, source_path="/foo")
        ok = rollback(r)
        assert ok is True
