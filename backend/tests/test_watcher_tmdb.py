import pytest
from pathlib import Path
import asyncio
from unittest.mock import AsyncMock, MagicMock
from backend.tmdb import TmdbClient, TmdbMatch
from backend.watcher import tmdb_async_resolve, process_directory, DownloadDirHandler, start_watcher
from backend.config import AppConfig, SeriesDB
from backend.models import BatchTriageJob, FileTriageItem, ParsedAnime, TriageStatus
import backend.main as main_api

@pytest.fixture
def clean_queue():
    main_api.queue.clear()
    yield
    main_api.queue.clear()

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if not self.ok:
            raise Exception("HTTP Error")

@pytest.mark.asyncio
async def test_tmdb_client_search_and_verify(monkeypatch):
    client = TmdbClient(api_key="test_key")
    assert client.api_key == "test_key"
    
    # Mock httpx.AsyncClient.get
    async def mock_get(self_client, url, **kwargs):
        if "search/tv" in url:
            return MockResponse({
                "results": [
                    {
                        "id": 100,
                        "name": "Frieren: Beyond Journey's End",
                        "original_name": "Sousou no Frieren",
                        "origin_country": ["JP"],
                        "genre_ids": [16]
                    }
                ]
            })
        elif "tv/100/season" in url:
            return MockResponse({}, status_code=200)
        elif "tv/100" in url:
            return MockResponse({
                "number_of_seasons": 1,
                "name": "葬送的芙莉莲",
                "alternative_titles": {
                    "results": [
                        {"title": "Sousou no Frieren"},
                        {"title": "Frieren"}
                    ]
                },
                "seasons": [
                    {"name": "Season 1", "season_number": 1}
                ]
            })
        return MockResponse({}, status_code=404)
        
    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    
    # Run search
    results = await client.search_anime("Frieren")
    assert len(results) == 1
    assert results[0].tmdb_id == 100
    assert results[0].name == "葬送的芙莉莲"
    assert results[0].confidence > 0.5
    
    # Run verify episode
    ok = await client.verify_episode(100, 1, 1)
    assert ok is True

@pytest.mark.asyncio
async def test_tmdb_async_resolve(monkeypatch, clean_queue):
    config = AppConfig(
        download_dir="/tmp",
        storage_dir="/tmp",
        tmdb_api_key="test_key",
        default_mode="confirm"
    )
    
    # Setup a pending job in queue
    job = BatchTriageJob(
        id="job123",
        source_dir="Frieren",
        items=[FileTriageItem(relative_path="Frieren/01.mkv", is_video=True)],
        status=TriageStatus.pending
    )
    main_api.queue["job123"] = job
    
    # Mock search_anime in TmdbClient
    async def mock_search_anime(self, title):
        return [
            TmdbMatch(
                tmdb_id=100,
                name="葬送的芙莉莲",
                original_name="Sousou no Frieren",
                season_count=1,
                confidence=0.95,
                matched_season=1
            )
        ]
    monkeypatch.setattr(TmdbClient, "search_anime", mock_search_anime)
    
    await tmdb_async_resolve("job123", "Frieren", "Frieren", config)
    
    updated_job = main_api.queue["job123"]
    assert updated_job.override_title == "葬送的芙莉莲"
    assert updated_job.series_config is not None
    assert updated_job.series_config.tmdb_name == "葬送的芙莉莲"

def test_process_directory(tmp_path):
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    
    # Create anime directories and files
    anime_dir = download_dir / "Frieren"
    anime_dir.mkdir()
    (anime_dir / "Frieren - 01.mkv").write_text("video")
    (anime_dir / "Frieren - 01.sc.ass").write_text("subtitle")
    
    config = AppConfig(
        download_dir=str(download_dir),
        storage_dir=str(tmp_path / "storage"),
        default_mode="confirm"
    )
    series_db = SeriesDB(str(tmp_path / "series.yaml"))
    
    job = process_directory(anime_dir, config, series_db, strict=False)
    assert job is not None
    assert job.source_dir == "Frieren"
    assert len(job.items) == 2
    assert any(it.is_video for it in job.items)

def test_watcher_handlers(tmp_path, clean_queue):
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    
    config = AppConfig(
        download_dir=str(download_dir),
        storage_dir=str(tmp_path / "storage"),
        default_mode="confirm"
    )
    series_db = SeriesDB(str(tmp_path / "series.yaml"))
    
    loop = MagicMock()
    handler = DownloadDirHandler(config, series_db, loop)
    
    # Trigger event on folder
    anime_dir = download_dir / "Frieren"
    anime_dir.mkdir()
    (anime_dir / "Frieren - 01.mkv").write_text("video")
    
    handler.process_dir_event(anime_dir, strict=False)
    
    assert len(main_api.queue) == 1
    job = list(main_api.queue.values())[0]
    assert job.source_dir == "Frieren"
    
    # Test file ignored state inheritance
    # Mark file as ignored
    job.items[0].ignored = True
    
    # Trigger another directory event, should preserve ignored status
    handler.process_dir_event(anime_dir, strict=False)
    updated_job = list(main_api.queue.values())[0]
    assert updated_job.items[0].ignored is True

def test_start_watcher(tmp_path, monkeypatch):
    # Mock watchdog Observer
    mock_observer = MagicMock()
    monkeypatch.setattr("backend.watcher.Observer", lambda: mock_observer)
    
    loop = MagicMock()
    observer = start_watcher(loop)
    assert observer == mock_observer
    assert mock_observer.schedule.called
    assert mock_observer.start.called
