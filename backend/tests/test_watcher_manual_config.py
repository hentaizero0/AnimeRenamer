import pytest
from pathlib import Path
from backend.watcher import is_download_root, get_root_mode, resolve_anime_dir_and_mode
import tempfile
import yaml
import json

def test_is_download_root(tmp_path):
    assert not is_download_root(tmp_path)
    
    # Test Bangumi
    bangumi = tmp_path / "Bangumi"
    bangumi.mkdir()
    assert not is_download_root(bangumi)
    (bangumi / "triage.yaml").write_text("mode: auto")
    assert is_download_root(bangumi)
    assert get_root_mode(bangumi) == "auto"
    
    # Test manual config yaml
    manual = tmp_path / "Manual"
    manual.mkdir()
    (manual / "triage.yaml").write_text("mode: confirm\n")
    assert is_download_root(manual)
    assert get_root_mode(manual) == "confirm"
    
    # Test manual config json
    manual_json = tmp_path / "ManualJSON"
    manual_json.mkdir()
    (manual_json / "triage.json").write_text('{"mode": "auto"}')
    assert is_download_root(manual_json)
    assert get_root_mode(manual_json) == "auto"

def test_resolve_anime_dir_and_mode(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    
    # Normal confirm
    anime1 = downloads / "Anime1"
    anime1.mkdir()
    res = resolve_anime_dir_and_mode(anime1 / "file.mkv", downloads)
    assert res is not None
    assert res[0] == anime1
    assert res[1] == "confirm"
    
    # Bangumi auto
    bangumi = downloads / "Bangumi"
    bangumi.mkdir()
    (bangumi / "triage.yaml").write_text("mode: auto")
    anime2 = bangumi / "Anime2"
    anime2.mkdir()
    res = resolve_anime_dir_and_mode(anime2 / "file.mkv", downloads)
    assert res is not None
    assert res[0] == anime2
    assert res[1] == "auto"
    
    # Manual confirm
    manual = downloads / "ManualFolder"
    manual.mkdir()
    (manual / "triage.yaml").write_text("mode: confirm\n")
    anime3 = manual / "Anime3"
    anime3.mkdir()
    res = resolve_anime_dir_and_mode(anime3 / "file.mkv", downloads)
    assert res is not None
    assert res[0] == anime3
    assert res[1] == "confirm"

