import pytest
import os
import shutil
from pathlib import Path
from backend.models import BatchTriageJob, FileTriageItem, ParsedAnime, TriageStatus, SeriesConfig
from backend.config import AppConfig
from backend.triage import rename_and_move, create_hardlink, execute_triage_job

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

class TestExecuteTriageJob:
    @pytest.fixture
    def setup_dirs(self, tmp_path):
        download_dir = tmp_path / "downloads"
        storage_dir = tmp_path / "storage"
        airing_dir = tmp_path / "airing"
        
        download_dir.mkdir()
        storage_dir.mkdir()
        airing_dir.mkdir()
        
        config = AppConfig(
            download_dir=str(download_dir),
            storage_dir=str(storage_dir),
            jellyfin_airing_dir=str(airing_dir),
            jellyfin_collect_dir=str(airing_dir),
            default_mode="confirm"
        )
        return download_dir, storage_dir, airing_dir, config

    @pytest.mark.asyncio
    async def test_execute_triage_basic(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        
        # Create a source file
        video_rel = "Frieren/Frieren - 01.mkv"
        video_src = download_dir / video_rel
        video_src.parent.mkdir(parents=True, exist_ok=True)
        video_src.write_text("video content")
        
        parsed = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
        item = FileTriageItem(relative_path=video_rel, parsed=parsed, is_video=True)
        job = BatchTriageJob(id="job1", source_dir="Frieren", items=[item])
        
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True
        
        dest_file = storage_dir / "Frieren" / "Season 01" / "Frieren S01E01.mkv"
        assert dest_file.exists()
        assert not video_src.exists()
        
        link_file = airing_dir / "Frieren" / "Season 01" / "Frieren S01E01.mkv"
        assert link_file.exists()

    @pytest.mark.asyncio
    async def test_execute_triage_with_subtitles(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        
        video_rel = "Frieren/Frieren - 02.mkv"
        sub_rel = "Frieren/Frieren - 02.sc.ass"
        
        (download_dir / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (download_dir / video_rel).write_text("video")
        (download_dir / sub_rel).write_text("subtitle")
        
        p_video = ParsedAnime(raw_filename="Frieren - 02.mkv", detected_title="Frieren", season=1, episode=2, extension="mkv", confidence=0.9)
        p_sub = ParsedAnime(raw_filename="Frieren - 02.sc.ass", detected_title="Frieren", season=1, episode=2, extension="sc.ass", confidence=0.9)
        
        item_v = FileTriageItem(relative_path=video_rel, parsed=p_video, is_video=True)
        item_s = FileTriageItem(relative_path=sub_rel, parsed=p_sub, is_video=False)
        
        job = BatchTriageJob(id="job2", source_dir="Frieren", items=[item_v, item_s])
        
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True
        
        assert (storage_dir / "Frieren" / "Season 01" / "Frieren S01E02.mkv").exists()
        assert (storage_dir / "Frieren" / "Season 01" / "Frieren S01E02.sc.ass").exists()
        assert (airing_dir / "Frieren" / "Season 01" / "Frieren S01E02.mkv").exists()
        assert (airing_dir / "Frieren" / "Season 01" / "Frieren S01E02.sc.ass").exists()

    @pytest.mark.asyncio
    async def test_execute_triage_skip_ignored(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        
        video_rel = "Frieren - 03.mkv"
        (download_dir / video_rel).write_text("video")
        
        p_video = ParsedAnime(raw_filename="Frieren - 03.mkv", detected_title="Frieren", season=1, episode=3, extension="mkv", confidence=0.9)
        item = FileTriageItem(relative_path=video_rel, parsed=p_video, is_video=True, ignored=True)
        
        job = BatchTriageJob(id="job3", source_dir=".", items=[item])
        
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True
        assert not (storage_dir / "Frieren" / "Season 01" / "Frieren S01E03.mkv").exists()
        assert (download_dir / video_rel).exists() # Ignored files should not be moved

    def test_moves_file_exception(self, tmp_path, monkeypatch):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        dst = tmp_path / "dest.mkv"
        import shutil
        def mock_move(*args, **kwargs):
            raise OSError("permission denied")
        monkeypatch.setattr(shutil, "move", mock_move)
        res = rename_and_move(src, dst, dry_run=False)
        assert res.success is False
        assert "permission denied" in res.error_msg

    def test_creates_hardlink_source_missing(self, tmp_path):
        src = tmp_path / "nonexistent.mkv"
        link = tmp_path / "link.mkv"
        res = create_hardlink(src, link, dry_run=False)
        assert res.success is False
        assert "Source does not exist" in res.error_msg

    def test_creates_hardlink_exception(self, tmp_path, monkeypatch):
        src = tmp_path / "source.mkv"
        src.write_text("data")
        link = tmp_path / "link.mkv"
        import os
        def mock_link(*args, **kwargs):
            raise OSError("no space left on device")
        monkeypatch.setattr(os, "link", mock_link)
        res = create_hardlink(src, link, dry_run=False)
        assert res.success is False
        assert "no space" in res.error_msg

    @pytest.mark.asyncio
    async def test_execute_triage_source_missing_skip(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        p_video = ParsedAnime(raw_filename="Frieren - 04.mkv", detected_title="Frieren", season=1, episode=4, extension="mkv")
        item = FileTriageItem(relative_path="Frieren/Frieren - 04.mkv", parsed=p_video, is_video=True)
        job = BatchTriageJob(id="job4", source_dir="Frieren", items=[item])
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True

    @pytest.mark.asyncio
    async def test_execute_triage_fallback_filename(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        sub_rel = "Frieren - 05.sc.ass"
        (download_dir / sub_rel).write_text("subtitle")
        p_sub = ParsedAnime(raw_filename="Frieren - 05.sc.ass", detected_title="Frieren", season=1, episode=5, extension="sc.ass")
        item = FileTriageItem(relative_path=sub_rel, parsed=p_sub, is_video=False)
        job = BatchTriageJob(id="job5", source_dir=".", items=[item])
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True
        assert (storage_dir / "Frieren" / "Season 01" / "Frieren S01E05.sc.ass").exists()

    @pytest.mark.asyncio
    async def test_execute_triage_move_fail(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        video_rel = "Frieren - 06.mkv"
        (download_dir / video_rel).write_text("video")
        
        dst_file = storage_dir / "Frieren" / "Season 01" / "Frieren S01E06.mkv"
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        dst_file.write_text("already exists")
        
        p_video = ParsedAnime(raw_filename="Frieren - 06.mkv", detected_title="Frieren", season=1, episode=6, extension="mkv")
        item = FileTriageItem(relative_path=video_rel, parsed=p_video, is_video=True)
        job = BatchTriageJob(id="job6", source_dir=".", items=[item])
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is False
        assert "already exists" in res.error_msg

    @pytest.mark.asyncio
    async def test_execute_triage_no_episode_extra(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        extra_rel = "behind_scenes.mkv"
        (download_dir / extra_rel).write_text("behind the scenes")
        
        p_extra = ParsedAnime(raw_filename="behind_scenes.mkv", detected_title="Frieren", season=None, episode=None, extension="mkv")
        item = FileTriageItem(relative_path=extra_rel, parsed=p_extra, is_video=True)
        job = BatchTriageJob(id="job7", source_dir=".", items=[item])
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True
        assert (storage_dir / "Frieren" / "behind_scenes.mkv").exists()

    @pytest.mark.asyncio
    async def test_execute_triage_no_episode_value_error(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        # File is outside job.source_dir, triggering ValueError in relative_to
        extra_rel = "OutsideFolder/extra.mkv"
        (download_dir / extra_rel).parent.mkdir(parents=True, exist_ok=True)
        (download_dir / extra_rel).write_text("extra")
        
        p_extra = ParsedAnime(raw_filename="extra.mkv", detected_title="Frieren", season=None, episode=None, extension="mkv")
        item = FileTriageItem(relative_path=extra_rel, parsed=p_extra, is_video=True)
        job = BatchTriageJob(id="job7_val_err", source_dir="Frieren", items=[item])
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True
        assert (storage_dir / "Frieren" / "extra.mkv").exists()

    @pytest.mark.asyncio
    async def test_execute_triage_cleanup_remaining_files(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        
        video_rel = "Frieren/Frieren - 01.mkv"
        (download_dir / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (download_dir / video_rel).write_text("video")
        
        # Create a remaining file that is NOT in the job items
        remaining_rel = "Frieren/remaining_metadata.nfo"
        (download_dir / remaining_rel).write_text("metadata content")
        
        p_video = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv")
        item = FileTriageItem(relative_path=video_rel, parsed=p_video, is_video=True)
        
        job = BatchTriageJob(id="job_cleanup", source_dir="Frieren", items=[item])
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True
        
        # Verify the remaining file was swept to storage and the source folder was deleted
        assert (storage_dir / "Frieren" / "remaining_metadata.nfo").exists()
        assert not (download_dir / "Frieren").exists()

    @pytest.mark.asyncio
    async def test_execute_triage_rmtree_exception(self, setup_dirs, monkeypatch):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        video_rel = "Frieren/Frieren - 07.mkv"
        (download_dir / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (download_dir / video_rel).write_text("video")
        
        p_video = ParsedAnime(raw_filename="Frieren - 07.mkv", detected_title="Frieren", season=1, episode=7, extension="mkv")
        item = FileTriageItem(relative_path=video_rel, parsed=p_video, is_video=True)
        job = BatchTriageJob(id="job8", source_dir="Frieren", items=[item])
        
        def mock_rmtree(*args, **kwargs):
            raise OSError("cannot delete")
        monkeypatch.setattr(shutil, "rmtree", mock_rmtree)
        
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True

    @pytest.mark.asyncio
    async def test_execute_triage_auto_mode(self, setup_dirs):
        download_dir, storage_dir, airing_dir, config = setup_dirs
        
        video_rel = "Frieren/Frieren - 08.mkv"
        (download_dir / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (download_dir / video_rel).write_text("video")
        
        p_video = ParsedAnime(raw_filename="Frieren - 08.mkv", detected_title="Frieren", season=1, episode=8, extension="mkv")
        item = FileTriageItem(relative_path=video_rel, parsed=p_video, is_video=True)
        s_conf = SeriesConfig(mode="auto", tmdb_name="Frieren", season=1)
        job = BatchTriageJob(id="job_auto_mode", source_dir="Frieren", items=[item], series_config=s_conf)
        
        res = await execute_triage_job(job, config, dry_run=False)
        assert res.success is True
        
        # In auto mode, it should be renamed in place in the downloads directory
        assert (download_dir / "Frieren" / "Frieren S01E08.mkv").exists()
        
        # And hardlinked into the airing directory without "Season XX" subfolder
        assert (airing_dir / "Frieren" / "Frieren S01E08.mkv").exists()
        
        # It should NOT be moved into the storage directory
        assert not (storage_dir / "Frieren" / "Season 01" / "Frieren S01E08.mkv").exists()
