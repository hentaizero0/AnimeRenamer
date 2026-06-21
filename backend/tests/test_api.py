import pytest
from fastapi.testclient import TestClient
from backend.main import app, queue, history
from backend.models import BatchTriageJob, FileTriageItem, ParsedAnime, TriageStatus, TriageResult, SeriesConfig

@pytest.fixture
def client():
    # Clear queue and history before each test to ensure test isolation
    queue.clear()
    history.clear()
    return TestClient(app)

def test_get_stats_empty(client):
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["pending"] == 0
    assert data["today"] == 0
    assert data["errors"] == 0

def test_get_stats_with_history_success_field_fix(client):
    # Test that stats doesn't throw AttributeError when history contains items
    res = TriageResult(success=True, source_path="/src", dest_path="/dst")
    history.append({
        "job_id": "job1",
        "result": res,
        "title": "Test Title"
    })
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["today"] == 1
    assert data["errors"] == 0

def test_get_stats_with_history_error(client):
    res = TriageResult(success=False, source_path="/src", error_msg="failed")
    history.append({
        "job_id": "job1",
        "result": res,
        "title": "Test Title"
    })
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["today"] == 1
    assert data["errors"] == 1

def test_get_pending_empty(client):
    response = client.get("/api/pending")
    assert response.status_code == 200
    assert response.json() == []

def test_get_pending_with_job(client):
    parsed = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
    item = FileTriageItem(relative_path="Frieren/Frieren - 01.mkv", parsed=parsed, is_video=True)
    job = BatchTriageJob(id="job123", source_dir="Frieren", items=[item], status=TriageStatus.pending)
    queue["job123"] = job
    
    response = client.get("/api/pending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "job123"
    assert data[0]["detected_title"] == "Frieren"

def test_get_ignored_list(client):
    parsed = ParsedAnime(raw_filename="unknown.txt", detected_title="unknown", season=None, episode=None, extension="txt", confidence=0.1)
    item = FileTriageItem(relative_path="unknown.txt", parsed=parsed, is_video=False)
    job = BatchTriageJob(id="ignored_job", source_dir=".", items=[item], status=TriageStatus.ignored, ignore_reason="no_video")
    queue["ignored_job"] = job
    
    response = client.get("/api/ignored")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "ignored_job"
    assert data[0]["reason"] == "no_video"

def test_skip_job(client):
    parsed = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
    item = FileTriageItem(relative_path="Frieren/Frieren - 01.mkv", parsed=parsed, is_video=True)
    job = BatchTriageJob(id="job_skip", source_dir="Frieren", items=[item], status=TriageStatus.pending)
    queue["job_skip"] = job
    
    response = client.post("/api/pending/job_skip/skip")
    assert response.status_code == 200
    assert response.json() == {"status": "skipped"}
    assert "job_skip" not in queue

def test_skip_job_not_found(client):
    response = client.post("/api/pending/nonexistent/skip")
    assert response.status_code == 404

def test_patch_job(client):
    parsed = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
    item = FileTriageItem(relative_path="Frieren/Frieren - 01.mkv", parsed=parsed, is_video=True)
    job = BatchTriageJob(id="job_patch", source_dir="Frieren", items=[item], status=TriageStatus.pending)
    queue["job_patch"] = job
    
    updates = {"title": "Frieren: Beyond Journey's End", "season": 2, "episode": 2}
    response = client.patch("/api/pending/job_patch", json=updates)
    assert response.status_code == 200
    data = response.json()
    assert data["override_title"] == "Frieren: Beyond Journey's End"
    assert data["override_season"] == 2
    assert data["override_episode"] == 2

def test_patch_job_not_found(client):
    response = client.patch("/api/pending/nonexistent", json={"title": "test"})
    assert response.status_code == 404

def test_get_recent_history(client):
    res = TriageResult(success=True, source_path="/src/Frieren", dest_path="/dst/Frieren")
    history.append({
        "job_id": "job_hist",
        "result": res,
        "title": "Frieren"
    })
    response = client.get("/api/recent")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "job_hist"
    assert data[0]["title"] == "Frieren"

def test_series_crud_endpoints(client):
    # Test Get Series
    response = client.get("/api/series")
    assert response.status_code == 200
    
    # Test Add Series
    new_series = {
        "mode": "auto",
        "tmdb_name": "Test Anime",
        "tmdb_id": 12345,
        "season": 1,
        "aliases": ["Test Alias"]
    }
    response = client.post("/api/series", json=new_series)
    assert response.status_code == 200
    assert response.json() == {"status": "added"}
    
    # Test Update Series
    updated_series = {
        "mode": "confirm",
        "tmdb_name": "Test Anime Updated",
        "tmdb_id": 12345,
        "season": 2,
        "aliases": ["Test Alias"]
    }
    response = client.put("/api/series/Test%20Anime", json=updated_series)
    assert response.status_code == 200
    assert response.json() == {"status": "updated"}
    
    # Test Delete Series
    response = client.delete("/api/series/Test%20Anime")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}

def test_delete_series_not_found(client):
    response = client.delete("/api/series/Nonexistent")
    assert response.status_code == 404

def test_toggle_ignore_not_found(client):
    response = client.post("/api/pending/nonexistent/items/0/toggle_ignore")
    assert response.status_code == 404

def test_toggle_ignore_index_out_of_bounds(client):
    parsed = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
    item = FileTriageItem(relative_path="Frieren/Frieren - 01.mkv", parsed=parsed, is_video=True)
    job = BatchTriageJob(id="job_toggle", source_dir="Frieren", items=[item], status=TriageStatus.pending)
    queue["job_toggle"] = job
    
    response = client.post("/api/pending/job_toggle/items/99/toggle_ignore")
    assert response.status_code == 404

def test_preview_job_not_found(client):
    response = client.get("/api/pending/nonexistent/preview")
    assert response.status_code == 404

def test_confirm_job_not_found(client):
    response = client.post("/api/pending/nonexistent/confirm")
    assert response.status_code == 404

from backend.main import config as main_config

def test_toggle_ignore_cascade_and_delete(client, tmp_path):
    old_download_dir = main_config.download_dir
    main_config.download_dir = str(tmp_path)
    try:
        video_rel = "Frieren/Frieren - 01.mkv"
        sub_rel1 = "Frieren/Frieren - 01.sc.ass"
        sub_rel2 = "Frieren/Frieren - 01.tc.ass"
        (tmp_path / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / video_rel).write_text("v")
        (tmp_path / sub_rel1).write_text("s1")
        (tmp_path / sub_rel2).write_text("s2")

        parsed_v = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
        parsed_s1 = ParsedAnime(raw_filename="Frieren - 01.sc.ass", detected_title="Frieren", season=1, episode=1, extension="sc.ass", confidence=0.9)
        parsed_s2 = ParsedAnime(raw_filename="Frieren - 01.tc.ass", detected_title="Frieren", season=1, episode=1, extension="tc.ass", confidence=0.9)

        item_v = FileTriageItem(relative_path=video_rel, parsed=parsed_v, is_video=True)
        item_s1 = FileTriageItem(relative_path=sub_rel1, parsed=parsed_s1, is_video=False)
        item_s2 = FileTriageItem(relative_path=sub_rel2, parsed=parsed_s2, is_video=False)

        job = BatchTriageJob(id="job_toggle_cascade", source_dir="Frieren", items=[item_v, item_s1, item_s2], status=TriageStatus.pending)
        queue["job_toggle_cascade"] = job

        response = client.post("/api/pending/job_toggle_cascade/items/0/toggle_ignore")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ignored"] is True
        assert len(data["deleted"]) == 0

        assert job.items[0].ignored is True
        assert job.items[1].ignored is True
        assert job.items[2].ignored is True

        # Files should STILL exist on disk after toggle
        assert (tmp_path / video_rel).exists()
        assert (tmp_path / sub_rel1).exists()
        assert (tmp_path / sub_rel2).exists()

        # Triggering a scan should now physically delete them
        scan_response = client.post("/api/scan")
        assert scan_response.status_code == 200
        
        # Files should no longer exist after scan
        assert not (tmp_path / video_rel).exists()
        assert not (tmp_path / sub_rel1).exists()
        assert not (tmp_path / sub_rel2).exists()
    finally:
        main_config.download_dir = old_download_dir

def test_preview_job(client, tmp_path):
    old_download_dir = main_config.download_dir
    old_jellyfin = main_config.jellyfin_airing_dir
    old_collect = main_config.jellyfin_collect_dir
    main_config.download_dir = str(tmp_path)
    main_config.jellyfin_airing_dir = str(tmp_path / "airing")
    main_config.jellyfin_collect_dir = str(tmp_path / "collect")
    try:
        video_rel = "Frieren/Frieren - 01.mkv"
        (tmp_path / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / video_rel).write_text("v")

        parsed = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
        item = FileTriageItem(relative_path=video_rel, parsed=parsed, is_video=True)
        job = BatchTriageJob(id="job_preview", source_dir="Frieren", items=[item], status=TriageStatus.pending)
        queue["job_preview"] = job

        response = client.get("/api/pending/job_preview/preview")
        assert response.status_code == 200
        data = response.json()
        assert data["anime_name"] == "Frieren"
        assert len(data["renamed"]) == 1
        assert data["renamed"][0]["new_name"] == "Frieren S01E01.mkv"
        assert data["renamed"][0]["hardlink_path"] is not None
        assert "collect" in data["renamed"][0]["hardlink_path"]
    finally:
        main_config.download_dir = old_download_dir
        main_config.jellyfin_airing_dir = old_jellyfin
        main_config.jellyfin_collect_dir = old_collect

def test_confirm_job(client, tmp_path):
    old_download_dir = main_config.download_dir
    old_storage_dir = main_config.storage_dir
    main_config.download_dir = str(tmp_path / "downloads")
    main_config.storage_dir = str(tmp_path / "storage")
    try:
        Path = __import__("pathlib").Path
        Path(main_config.download_dir).mkdir(parents=True, exist_ok=True)
        Path(main_config.storage_dir).mkdir(parents=True, exist_ok=True)

        video_rel = "Frieren/Frieren - 01.mkv"
        (Path(main_config.download_dir) / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (Path(main_config.download_dir) / video_rel).write_text("v")

        parsed = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
        item = FileTriageItem(relative_path=video_rel, parsed=parsed, is_video=True)
        job = BatchTriageJob(id="job_confirm", source_dir="Frieren", items=[item], status=TriageStatus.pending)
        queue["job_confirm"] = job

        response = client.post("/api/pending/job_confirm/confirm")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert (Path(main_config.storage_dir) / "Frieren" / "Season 01" / "Frieren S01E01.mkv").exists()
    finally:
        main_config.download_dir = old_download_dir
        main_config.storage_dir = old_storage_dir

def test_confirm_job_with_ignored_files(client, tmp_path):
    old_download_dir = main_config.download_dir
    old_storage_dir = main_config.storage_dir
    main_config.download_dir = str(tmp_path / "downloads")
    main_config.storage_dir = str(tmp_path / "storage")
    try:
        Path = __import__("pathlib").Path
        Path(main_config.download_dir).mkdir(parents=True, exist_ok=True)
        Path(main_config.storage_dir).mkdir(parents=True, exist_ok=True)

        video_keep = "Frieren/Frieren - 01.mkv"
        video_ignore = "Frieren/Frieren - 01.bad.mkv"
        
        (Path(main_config.download_dir) / video_keep).parent.mkdir(parents=True, exist_ok=True)
        (Path(main_config.download_dir) / video_keep).write_text("keep")
        (Path(main_config.download_dir) / video_ignore).write_text("ignore")

        parsed_keep = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
        parsed_ignore = ParsedAnime(raw_filename="Frieren - 01.bad.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
        
        item_keep = FileTriageItem(relative_path=video_keep, parsed=parsed_keep, is_video=True)
        item_ignore = FileTriageItem(relative_path=video_ignore, parsed=parsed_ignore, is_video=True, ignored=True)
        
        job = BatchTriageJob(id="job_confirm_ignored", source_dir="Frieren", items=[item_keep, item_ignore], status=TriageStatus.pending)
        queue["job_confirm_ignored"] = job

        response = client.post("/api/pending/job_confirm_ignored/confirm")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Kept file should be moved to storage
        assert (Path(main_config.storage_dir) / "Frieren" / "Season 01" / "Frieren S01E01.mkv").exists()
        # Ignored file should NOT be moved to storage
        assert not (Path(main_config.storage_dir) / "Frieren" / "Season 01" / "Frieren S01E01.bad.mkv").exists()
        # The download folder and files should be cleaned up completely
        assert not (Path(main_config.download_dir) / video_keep).exists()
        assert not (Path(main_config.download_dir) / video_ignore).exists()
        assert not (Path(main_config.download_dir) / "Frieren").exists()
    finally:
        main_config.download_dir = old_download_dir
        main_config.storage_dir = old_storage_dir

def test_merge_suggestions(client):
    parsed_a = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv")
    item_a = FileTriageItem(relative_path="Frieren/Frieren - 01.mkv", parsed=parsed_a, is_video=True)
    job_a = BatchTriageJob(id="job_a", source_dir="Frieren A", items=[item_a], status=TriageStatus.pending)
    
    parsed_b = ParsedAnime(raw_filename="Frieren - 04.mkv", detected_title="Frieren", season=1, episode=4, extension="mkv")
    item_b = FileTriageItem(relative_path="Frieren/Frieren - 04.mkv", parsed=parsed_b, is_video=True)
    job_b = BatchTriageJob(id="job_b", source_dir="Frieren B", items=[item_b], status=TriageStatus.pending)
    
    queue["job_a"] = job_a
    queue["job_b"] = job_b
    
    response = client.get("/api/pending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    
    item_a_res = [x for x in data if x["id"] == "job_a"][0]
    item_b_res = [x for x in data if x["id"] == "job_b"][0]
    
    assert item_a_res["merge_suggestion"]["merge_with_id"] == "job_b"
    assert item_b_res["merge_suggestion"]["merge_with_id"] == "job_a"

def test_trigger_scan(client, tmp_path):
    old_download_dir = main_config.download_dir
    main_config.download_dir = str(tmp_path)
    try:
        (tmp_path / "Bangumi" / "Frieren").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Bangumi" / "Frieren" / "01.mkv").write_text("v")
        
        response = client.post("/api/scan")
        assert response.status_code == 200
        data = response.json()
        assert "scan triggered" in data["status"]
    finally:
        main_config.download_dir = old_download_dir

def test_get_pending_retains_ignored_duplicates(client):
    parsed_v1 = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv")
    parsed_v2 = ParsedAnime(raw_filename="Frieren - 01.bad.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv")
    item_v1 = FileTriageItem(relative_path="Frieren/Frieren - 01.mkv", parsed=parsed_v1, is_video=True)
    item_v2 = FileTriageItem(relative_path="Frieren/Frieren - 01.bad.mkv", parsed=parsed_v2, is_video=True, ignored=True)
    job = BatchTriageJob(id="job_dup_ignored", source_dir="Frieren", items=[item_v1, item_v2], status=TriageStatus.pending)
    queue["job_dup_ignored"] = job
    
    response = client.get("/api/pending")
    assert response.status_code == 200
    data = response.json()
    job_res = [x for x in data if x["id"] == "job_dup_ignored"][0]
    
    assert "1" in job_res["duplicates"]
    assert len(job_res["duplicates"]["1"]) == 2

def test_preview_job_auto_mode(client, tmp_path):
    old_download_dir = main_config.download_dir
    old_jellyfin = main_config.jellyfin_airing_dir
    main_config.download_dir = str(tmp_path)
    main_config.jellyfin_airing_dir = str(tmp_path / "airing")
    try:
        video_rel = "Frieren/Frieren - 01.mkv"
        (tmp_path / video_rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / video_rel).write_text("v")

        parsed = ParsedAnime(raw_filename="Frieren - 01.mkv", detected_title="Frieren", season=1, episode=1, extension="mkv", confidence=0.9)
        item = FileTriageItem(relative_path=video_rel, parsed=parsed, is_video=True)
        s_conf = SeriesConfig(mode="auto", tmdb_name="Frieren", season=1)
        job = BatchTriageJob(id="job_preview_auto", source_dir="Frieren", items=[item], series_config=s_conf, status=TriageStatus.pending)
        queue["job_preview_auto"] = job

        response = client.get("/api/pending/job_preview_auto/preview")
        assert response.status_code == 200
        data = response.json()
        assert data["renamed"][0]["hardlink_path"] is not None
        assert "airing" in data["renamed"][0]["hardlink_path"]
    finally:
        main_config.download_dir = old_download_dir
        main_config.jellyfin_airing_dir = old_jellyfin

def test_get_directories(client, tmp_path):
    old_download_dir = main_config.download_dir
    main_config.download_dir = str(tmp_path)
    try:
        Path = __import__("pathlib").Path
        (tmp_path / "Bangumi").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Manual").mkdir(parents=True, exist_ok=True)
        (tmp_path / "Manual" / "triage.yaml").write_text("mode: confirm")
        (tmp_path / "Other").mkdir(parents=True, exist_ok=True)
        
        response = client.get("/api/directories")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        
        bangumi = next(x for x in data if x["name"] == "Bangumi")
        assert bangumi["is_root"] is False
        assert bangumi["mode"] == "confirm"
        assert bangumi["has_yaml"] is False
        
        manual = next(x for x in data if x["name"] == "Manual")
        assert manual["is_root"] is True
        assert manual["mode"] == "confirm"
        assert manual["has_yaml"] is True
        
        other = next(x for x in data if x["name"] == "Other")
        assert other["is_root"] is False
        assert other["mode"] == "confirm"
        assert other["has_yaml"] is False
    finally:
        main_config.download_dir = old_download_dir

def test_update_directory_mode(client, tmp_path):
    old_download_dir = main_config.download_dir
    main_config.download_dir = str(tmp_path)
    try:
        Path = __import__("pathlib").Path
        (tmp_path / "MySeries").mkdir(parents=True, exist_ok=True)
        
        # Test setting to auto
        response = client.post("/api/directories/MySeries/mode", json={"mode": "auto"})
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "auto"
        
        # Verify file created
        yaml_path = tmp_path / "MySeries" / "triage.yaml"
        assert yaml_path.exists()
        assert "mode: auto" in yaml_path.read_text()
        
        # Test setting back to confirm
        response = client.post("/api/directories/MySeries/mode", json={"mode": "confirm"})
        assert response.status_code == 200
        assert "mode: confirm" in yaml_path.read_text()
        
    finally:
        main_config.download_dir = old_download_dir

