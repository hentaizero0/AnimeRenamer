import os
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.models import SeriesConfig

class AppConfig(BaseSettings):
    tmdb_api_key: str = Field(default="", description="TMDB API Key")
    confidence_threshold: float = 0.85
    default_mode: Literal["auto", "confirm"] = "confirm"
    download_dir: Path = Path("/downloads")
    storage_dir: Path = Path("/anime")
    jellyfin_airing_dir: Path = Path("/jellyfin/airing")
    jellyfin_collect_dir: Path = Path("/jellyfin/anime")

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

def load_config(config_path: Path | str = "/app/config/series_config.yaml") -> AppConfig:
    config_path = Path(config_path)
    yaml_settings = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            yaml_settings = data.get("settings", {})
    
    # Check if tmdb_api_key is an env var template
    if "tmdb_api_key" in yaml_settings and yaml_settings["tmdb_api_key"] == "${TMDB_API_KEY}":
        yaml_settings["tmdb_api_key"] = os.environ.get("TMDB_API_KEY", "")
        
    return AppConfig(**yaml_settings)

class SeriesDB:
    def __init__(self, config_path: Path | str = "/app/config/series_config.yaml"):
        self.config_path = Path(config_path)
        self._series: dict[str, SeriesConfig] = {}
        self.reload()

    def reload(self) -> None:
        self._series.clear()
        if not self.config_path.exists():
            return
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            series_data = data.get("series", {})
            for title, s_conf in series_data.items():
                self._series[title] = SeriesConfig(**s_conf)

    def save(self) -> None:
        data = {}
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                
        series_dict = {}
        for title, s_conf in self._series.items():
            series_dict[title] = s_conf.model_dump(exclude_none=True)
            
        data["series"] = series_dict
        
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    def get(self, title: str) -> SeriesConfig | None:
        return self._series.get(title)

    def match_entry_by_alias(self, raw_title: str) -> tuple[str, SeriesConfig] | None:
        raw_lower = raw_title.lower()
        for title, s_conf in self._series.items():
            if title.lower() == raw_lower or s_conf.tmdb_name.lower() == raw_lower:
                return title, s_conf
            for alias in s_conf.aliases:
                if alias.lower() == raw_lower:
                    return title, s_conf
        return None

    def match_by_alias(self, raw_title: str) -> SeriesConfig | None:
        matched = self.match_entry_by_alias(raw_title)
        return matched[1] if matched else None

    def add(self, series: SeriesConfig, title: str | None = None) -> None:
        key = title or series.tmdb_name
        self._series[key] = series
        self.save()
