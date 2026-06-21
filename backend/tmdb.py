from dataclasses import dataclass
from typing import Any
import httpx
from rapidfuzz import fuzz

@dataclass
class TmdbMatch:
    tmdb_id: int
    name: str
    original_name: str
    season_count: int
    confidence: float

class TmdbClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.themoviedb.org/3"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "accept": "application/json",
        }
        # If API key is simple string vs Bearer token
        if not self.api_key.startswith("ey"):
            self.headers = {"accept": "application/json"}
            self.params = {"api_key": self.api_key}
        else:
            self.params = {}

    async def search_anime(self, title: str, season: int | None = None) -> list[TmdbMatch]:
        if not self.api_key:
            return []
            
        async with httpx.AsyncClient() as client:
            try:
                # Search TV shows
                params = {**self.params, "query": title, "language": "zh-CN"}
                # If using api_key param, we don't need auth header
                headers = self.headers if "Authorization" in self.headers else {"accept": "application/json"}
                
                resp = await client.get(
                    f"{self.base_url}/search/tv",
                    params=params,
                    headers=headers,
                    timeout=10.0
                )
                resp.raise_for_status()
                data = resp.json()
                
                results = []
                for item in data.get("results", []):
                    tmdb_id = item["id"]
                    name = item.get("name", "")
                    original_name = item.get("original_name", "")
                    
                    # Fetch details to get season count
                    details_resp = await client.get(
                        f"{self.base_url}/tv/{tmdb_id}",
                        params={**self.params, "language": "zh-CN"},
                        headers=headers,
                        timeout=10.0
                    )
                    details = {}
                    if details_resp.status_code == 200:
                        details = details_resp.json()
                        
                    season_count = details.get("number_of_seasons", 1)
                    
                    # Calculate confidence
                    # Base confidence on name similarity
                    sim1 = fuzz.ratio(title.lower(), name.lower()) / 100.0
                    sim2 = fuzz.ratio(title.lower(), original_name.lower()) / 100.0
                    base_conf = max(sim1, sim2) * 0.7
                    
                    # Boosts
                    boost = 0.0
                    if item.get("origin_country") and "JP" in item.get("origin_country"):
                        boost += 0.1
                    if 16 in item.get("genre_ids", []): # 16 is Animation
                        boost += 0.1
                        
                    conf = min(1.0, base_conf + boost)
                    
                    results.append(TmdbMatch(
                        tmdb_id=tmdb_id,
                        name=name,
                        original_name=original_name,
                        season_count=season_count,
                        confidence=conf
                    ))
                
                # Sort by confidence descending
                results.sort(key=lambda x: x.confidence, reverse=True)
                return results
            except Exception as e:
                print(f"TMDB search error: {e}")
                return []

    async def verify_episode(self, tmdb_id: int, season: int, episode: int) -> bool:
        if not self.api_key:
            return False
            
        async with httpx.AsyncClient() as client:
            try:
                headers = self.headers if "Authorization" in self.headers else {"accept": "application/json"}
                resp = await client.get(
                    f"{self.base_url}/tv/{tmdb_id}/season/{season}/episode/{episode}",
                    params=self.params,
                    headers=headers,
                    timeout=10.0
                )
                return resp.status_code == 200
            except Exception:
                return False
