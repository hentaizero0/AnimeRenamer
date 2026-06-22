from backend.config import load_config
from backend.watcher import find_all_anime_dirs
from pathlib import Path

config = load_config("config/series_config.yaml")
res = find_all_anime_dirs(Path(config.download_dir))
print("FOUND:", [str(d[0].relative_to(config.download_dir)) for d in res])
