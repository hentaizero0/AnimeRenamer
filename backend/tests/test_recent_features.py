import pytest
from pathlib import Path
import json
import yaml

from backend.watcher import (
    is_download_root, get_root_mode, resolve_anime_dir_and_mode,
    find_all_anime_dirs, process_directory
)
from backend.models import BatchTriageJob, FileTriageItem, ParsedAnime, TriageStatus, SeriesConfig
from backend.triage import execute_triage_job
from backend.main import app, queue, config
from fastapi.testclient import TestClient

client = TestClient(app)

# --- WATCHER ROOT LOGIC TESTS (1-6) ---
def test_1_is_download_root_bangumi_collection(tmp_path):
    # Unconfigured BangumiCollection is no longer a root
    d = tmp_path / "BangumiCollection"
    d.mkdir()
    assert is_download_root(d) is False
    assert get_root_mode(d) == "confirm"
    
    # Configured BangumiCollection is a root
    (d / "triage.yaml").write_text("mode: auto")
    assert is_download_root(d) is True
    assert get_root_mode(d) == "auto"

def test_2_is_download_root_invalid_json(tmp_path):
    d = tmp_path / "BadJson"
    d.mkdir()
    (d / "triage.json").write_text("{bad json}")
    assert is_download_root(d) is False # json parse fails, returns None

def test_3_resolve_anime_dir_multi_level(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    root = downloads / "MyRoot"
    root.mkdir()
    (root / "triage.yaml").write_text("mode: auto")
    anime = root / "Group" / "Anime Title"
    anime.mkdir(parents=True)
    res = resolve_anime_dir_and_mode(anime / "file.mkv", downloads)
    assert res is not None
    assert res[0] == root / "Group" / "Anime Title" # The real leaf with media
    assert res[1] == "auto"

def test_4_find_all_anime_dirs_mixed(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    
    # Root A
    (downloads / "Bangumi").mkdir(parents=True)
    (downloads / "Bangumi" / "triage.yaml").write_text("mode: auto")
    (downloads / "Bangumi" / "Anime A").mkdir(parents=True)
    (downloads / "Bangumi" / "Anime A" / "1.mkv").touch()
    # Root B
    (downloads / "ManualRoot").mkdir()
    (downloads / "ManualRoot" / "triage.yaml").write_text("mode: confirm")
    (downloads / "ManualRoot" / "Anime B").mkdir()
    (downloads / "ManualRoot" / "Anime B" / "1.mkv").touch()
    # Normal dir
    (downloads / "Anime C").mkdir()
    (downloads / "Anime C" / "1.mkv").touch()
    
    dirs = find_all_anime_dirs(downloads)
    paths = [str(d[0].relative_to(downloads)) for d in dirs]
    assert "Bangumi/Anime A" in paths
    assert "ManualRoot/Anime B" in paths
    assert "Anime C" in paths

def test_5_find_all_anime_dirs_nested_roots(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    
    root = downloads / "Root1"
    root.mkdir()
    (root / "triage.yaml").write_text("mode: confirm")
    subroot = root / "Root2"
    subroot.mkdir()
    (subroot / "triage.yaml").write_text("mode: auto")
    (subroot / "Anime D").mkdir()
    (subroot / "Anime D" / "1.mkv").touch()
    
    dirs = find_all_anime_dirs(downloads)
    paths = {str(d[0].relative_to(downloads)): d[1] for d in dirs}
    assert "Root1/Root2/Anime D" in paths
    assert paths["Root1/Root2/Anime D"] == "auto"

def test_6_process_directory_ignores_non_media(tmp_path):
    class DummyConfig:
        download_dir = str(tmp_path)
    
    anime = tmp_path / "Anime E"
    anime.mkdir()
    (anime / "test.txt").write_text("info")
    (anime / "cover.jpg").write_text("img")
    
    job = process_directory(anime, DummyConfig(), None)
    assert job is not None
    assert job.status == TriageStatus.ignored
    assert job.ignore_reason == "no_video"
    assert len(job.items) == 0

# --- TRIAGE LOGIC TESTS (7-12) ---
@pytest.fixture
def setup_triage_dirs(tmp_path):
    class Config:
        download_dir = str(tmp_path / "dl")
        storage_dir = str(tmp_path / "st")
        jellyfin_airing_dir = str(tmp_path / "air")
        jellyfin_collect_dir = str(tmp_path / "col")
        default_mode = "confirm"
    
    (tmp_path / "dl").mkdir()
    (tmp_path / "st").mkdir()
    (tmp_path / "air").mkdir()
    (tmp_path / "col").mkdir()
    return Config(), tmp_path / "dl", tmp_path / "st", tmp_path / "air", tmp_path / "col"

@pytest.mark.asyncio
async def test_7_auto_mode_sub_hardlink(setup_triage_dirs):
    config, dl, st, air, col = setup_triage_dirs
    (dl / "Anime F").mkdir()
    (dl / "Anime F" / "01.mkv").write_text("v")
    (dl / "Anime F" / "01.srt").write_text("s")
    
    pv = ParsedAnime(raw_filename="01.mkv", detected_title="Anime F", season=1, episode=1, extension="mkv")
    ps = ParsedAnime(raw_filename="01.srt", detected_title="Anime F", season=1, episode=1, extension="srt")
    
    job = BatchTriageJob(id="j7", source_dir="Anime F", default_mode="auto", 
                         items=[FileTriageItem(relative_path="Anime F/01.mkv", parsed=pv, is_video=True),
                                FileTriageItem(relative_path="Anime F/01.srt", parsed=ps, is_video=False)])
    
    await execute_triage_job(job, config)
    assert (air / "Anime F" / "Anime F S01E01.mkv").exists()
    assert (air / "Anime F" / "Anime F S01E01.srt").exists()

@pytest.mark.asyncio
async def test_8_confirm_mode_sub_hardlink(setup_triage_dirs):
    config, dl, st, air, col = setup_triage_dirs
    (dl / "Anime G").mkdir()
    (dl / "Anime G" / "02.mkv").write_text("v")
    (dl / "Anime G" / "02.ass").write_text("s")
    
    pv = ParsedAnime(raw_filename="02.mkv", detected_title="Anime G", season=1, episode=2, extension="mkv")
    ps = ParsedAnime(raw_filename="02.ass", detected_title="Anime G", season=1, episode=2, extension="ass")
    
    job = BatchTriageJob(id="j8", source_dir="Anime G", default_mode="confirm", 
                         items=[FileTriageItem(relative_path="Anime G/02.mkv", parsed=pv, is_video=True),
                                FileTriageItem(relative_path="Anime G/02.ass", parsed=ps, is_video=False)])
    
    await execute_triage_job(job, config)
    assert (col / "Anime G" / "Season 01" / "Anime G S01E02.mkv").exists()
    assert (col / "Anime G" / "Season 01" / "Anime G S01E02.ass").exists()

@pytest.mark.asyncio
async def test_8b_confirm_mode_extras_stay_in_season_without_hardlink(setup_triage_dirs):
    config, dl, st, air, col = setup_triage_dirs
    (dl / "Anime G" / "NCOP").mkdir(parents=True)
    (dl / "Anime G" / "NCOP" / "creditless.mkv").write_text("v")

    job = BatchTriageJob(
        id="j8b",
        source_dir="Anime G",
        default_mode="confirm",
        items=[FileTriageItem(relative_path="Anime G/NCOP/creditless.mkv", parsed=None, is_video=True)],
    )

    await execute_triage_job(job, config)
    assert (st / "Anime G" / "Season 01" / "NCOP" / "creditless.mkv").exists()
    assert not (col / "Anime G" / "Season 01" / "NCOP" / "creditless.mkv").exists()

@pytest.mark.asyncio
async def test_9_auto_mode_without_episode(setup_triage_dirs):
    config, dl, st, air, col = setup_triage_dirs
    (dl / "Anime H").mkdir()
    (dl / "Anime H" / "Movie.mkv").write_text("v")
    
    pv = ParsedAnime(raw_filename="Movie.mkv", detected_title="Anime H", season=None, episode=None, extension="mkv")
    job = BatchTriageJob(id="j9", source_dir="Anime H", default_mode="auto", 
                         items=[FileTriageItem(relative_path="Anime H/Movie.mkv", parsed=pv, is_video=True)])
    
    await execute_triage_job(job, config)
    # Target should be just the file itself in auto mode
    assert (dl / "Anime H" / "Movie.mkv").exists()
    assert (air / "Anime H" / "Movie.mkv").exists()

@pytest.mark.asyncio
async def test_10_auto_mode_identical_source(setup_triage_dirs):
    config, dl, st, air, col = setup_triage_dirs
    (dl / "Anime I").mkdir()
    (dl / "Anime I" / "Anime I S01E03.mkv").write_text("v")
    
    pv = ParsedAnime(raw_filename="Anime I S01E03.mkv", detected_title="Anime I", season=1, episode=3, extension="mkv")
    job = BatchTriageJob(id="j10", source_dir="Anime I", default_mode="auto", 
                         items=[FileTriageItem(relative_path="Anime I/Anime I S01E03.mkv", parsed=pv, is_video=True)])
    
    res = await execute_triage_job(job, config)
    assert res.success is True
    assert (air / "Anime I" / "Anime I S01E03.mkv").exists()

@pytest.mark.asyncio
async def test_11_confirm_mode_cleans_up_source(setup_triage_dirs):
    config, dl, st, air, col = setup_triage_dirs
    (dl / "Anime J").mkdir()
    (dl / "Anime J" / "04.mkv").write_text("v")
    (dl / "Anime J" / "trash.txt").write_text("t")
    
    pv = ParsedAnime(raw_filename="04.mkv", detected_title="Anime J", season=1, episode=4, extension="mkv")
    job = BatchTriageJob(id="j11", source_dir="Anime J", default_mode="confirm", 
                         items=[FileTriageItem(relative_path="Anime J/04.mkv", parsed=pv, is_video=True)])
    
    await execute_triage_job(job, config)
    assert not (dl / "Anime J").exists()

@pytest.mark.asyncio
async def test_12_auto_mode_keeps_source_directory(setup_triage_dirs):
    config, dl, st, air, col = setup_triage_dirs
    (dl / "Anime K").mkdir()
    (dl / "Anime K" / "05.mkv").write_text("v")
    (dl / "Anime K" / "trash.txt").write_text("t")
    
    pv = ParsedAnime(raw_filename="05.mkv", detected_title="Anime K", season=1, episode=5, extension="mkv")
    job = BatchTriageJob(id="j12", source_dir="Anime K", default_mode="auto", 
                         items=[FileTriageItem(relative_path="Anime K/05.mkv", parsed=pv, is_video=True)])
    
    await execute_triage_job(job, config)
    assert (dl / "Anime K").exists()
    assert (dl / "Anime K" / "trash.txt").exists()

# --- ENDPOINT & DEFERRED DELETION TESTS (13-20) ---
@pytest.fixture
def mock_main_dirs(tmp_path):
    old_dl = config.download_dir
    config.download_dir = str(tmp_path / "dl")
    Path(config.download_dir).mkdir(parents=True, exist_ok=True)
    yield tmp_path / "dl"
    config.download_dir = old_dl

def test_13_scan_deletes_ignored_files(mock_main_dirs):
    dl = mock_main_dirs
    (dl / "Anime L").mkdir()
    file_path = dl / "Anime L" / "bad.mkv"
    file_path.write_text("v")
    
    job = BatchTriageJob(id="j13", source_dir="Anime L", status=TriageStatus.pending,
                         items=[FileTriageItem(relative_path="Anime L/bad.mkv", parsed=None, is_video=True, ignored=True)])
    queue["j13"] = job
    
    client.post("/api/scan")
    assert not file_path.exists()
    if "j13" in queue:
        del queue["j13"]

def test_14_scan_leaves_non_ignored(mock_main_dirs):
    dl = mock_main_dirs
    (dl / "Anime M").mkdir()
    file_path = dl / "Anime M" / "good.mkv"
    file_path.write_text("v")
    
    job = BatchTriageJob(id="j14", source_dir="Anime M", status=TriageStatus.pending,
                         items=[FileTriageItem(relative_path="Anime M/good.mkv", parsed=None, is_video=True, ignored=False)])
    queue["j14"] = job
    
    client.post("/api/scan")
    assert file_path.exists()
    if "j14" in queue:
        del queue["j14"]

def test_15_confirm_deletes_ignored(mock_main_dirs, monkeypatch):
    # we patch execute_triage_job so we just test the deletion logic in the route
    from backend import main as main_module
    async def mock_exec(*args, **kwargs):
        from backend.models import TriageResult
        return TriageResult(success=True, source_path="", dest_path="")
    monkeypatch.setattr(main_module, "execute_triage_job", mock_exec)
    
    dl = mock_main_dirs
    (dl / "Anime N").mkdir()
    file_path = dl / "Anime N" / "bad.mkv"
    file_path.write_text("v")
    
    job = BatchTriageJob(id="j15", source_dir="Anime N", status=TriageStatus.pending,
                         items=[FileTriageItem(relative_path="Anime N/bad.mkv", parsed=None, is_video=True, ignored=True)])
    queue["j15"] = job
    
    client.post("/api/pending/j15/confirm")
    assert not file_path.exists()

def test_16_directories_returns_hidden_yaml(mock_main_dirs):
    dl = mock_main_dirs
    (dl / "Dir O").mkdir()
    (dl / "Dir O" / ".triage.yaml").write_text("mode: confirm")
    
    res = client.get("/api/directories").json()
    item = next(x for x in res if x["name"] == "Dir O")
    assert item["has_yaml"] is True

def test_17_directories_sorts_by_name(mock_main_dirs):
    dl = mock_main_dirs
    (dl / "Zeta").mkdir()
    (dl / "Alpha").mkdir()
    (dl / "Gamma").mkdir()
    
    res = client.get("/api/directories").json()
    names = [x["name"] for x in res if x["name"] in ["Zeta", "Alpha", "Gamma"]]
    assert names == ["Alpha", "Gamma", "Zeta"]

def test_18_update_mode_deletes_other_configs(mock_main_dirs):
    dl = mock_main_dirs
    d = dl / "Dir P"
    d.mkdir()
    (d / ".triage.yaml").write_text("hidden")
    (d / "triage.json").write_text("{}")
    
    client.post("/api/directories/Dir P/mode", json={"mode": "auto"})
    
    assert not (d / ".triage.yaml").exists()
    assert not (d / "triage.json").exists()
    assert (d / "triage.yaml").exists()

def test_19_update_mode_path_traversal(mock_main_dirs):
    res = client.post("/api/directories/..%2F..%2Fetc/mode", json={"mode": "auto"})
    assert res.status_code == 400

def test_20_update_mode_404(mock_main_dirs):
    res = client.post("/api/directories/Nonexistent/mode", json={"mode": "auto"})
    assert res.status_code == 404
