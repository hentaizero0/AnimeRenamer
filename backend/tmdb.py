from dataclasses import dataclass, field
from typing import Any, ClassVar
import re
import httpx
from rapidfuzz import fuzz

@dataclass
class TmdbMatch:
    tmdb_id: int
    name: str
    original_name: str
    season_count: int
    confidence: float
    matched_season: int | None = None
    season_names: dict[int, str] = field(default_factory=dict)
    backdrop_path: str | None = None

class TmdbClient:
    _shared_clients: ClassVar[dict[tuple[str, tuple[tuple[str, str], ...]], httpx.AsyncClient]] = {}

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

    def _client_key(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return self.api_key, tuple(sorted(self.headers.items()))

    def _get_client(self) -> httpx.AsyncClient:
        key = self._client_key()
        client = self._shared_clients.get(key)
        if client is None:
            client = httpx.AsyncClient()
            self._shared_clients[key] = client
        return client

    @classmethod
    async def aclose_all(cls) -> None:
        for client in cls._shared_clients.values():
            await client.aclose()
        cls._shared_clients.clear()

    async def search_anime(self, title: str) -> list[TmdbMatch]:
        if not self.api_key:
            return []

        client = self._get_client()
        zh_results = await self._search_once(client, title, language="zh-CN")

        # Use only zh_results to ensure names are always Chinese
        results = sorted(zh_results, key=lambda x: x.confidence, reverse=True)
        return results

    async def validate_key(self) -> bool:
        if not self.api_key:
            return False

        client = self._get_client()
        try:
            headers = self.headers if "Authorization" in self.headers else {"accept": "application/json"}
            resp = await client.get(
                f"{self.base_url}/configuration",
                params=self.params,
                headers=headers,
                timeout=5.0,
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def get_series_backdrop_path(self, tmdb_id: int) -> str | None:
        client = self._get_client()
        try:
            headers = self.headers if "Authorization" in self.headers else {"accept": "application/json"}
            resp = await client.get(
                f"{self.base_url}/tv/{tmdb_id}",
                params=self.params,
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code != 200:
                return None
            path = resp.json().get("backdrop_path")
            return path if isinstance(path, str) and path.startswith("/") else None
        except Exception:
            return None

    async def _search_once(self, client: httpx.AsyncClient, title: str, language: str) -> list[TmdbMatch]:
        try:
            # Search WITHOUT language so TMDB matches English/Romaji queries accurately
            params = {**self.params, "query": title}
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
                # The name returned from search (often English or original language)
                search_matched_name = item.get("name", "")
                original_name = item.get("original_name", "")
                
                # Fetch details WITH language to get Chinese translations and alternative titles
                details_resp = await client.get(
                    f"{self.base_url}/tv/{tmdb_id}",
                    params={**self.params, "language": language, "append_to_response": "alternative_titles"},
                    headers=headers,
                    timeout=10.0
                )
                # Fetch details WITHOUT language to get English/Romaji season names
                details_resp_en = await client.get(
                    f"{self.base_url}/tv/{tmdb_id}",
                    params={**self.params, "append_to_response": "alternative_titles"},
                    headers=headers,
                    timeout=10.0
                )
                final_name = search_matched_name
                details = {}
                details_en = {}
                if details_resp.status_code == 200:
                    details = details_resp.json()
                    # Final name to save will be the localized detail name (Chinese)
                    if details.get("name"):
                        final_name = details["name"]
                if details_resp_en.status_code == 200:
                    details_en = details_resp_en.json()
                    
                season_count = details.get("number_of_seasons", 1)
                
                # Match confidence against the name that search returned (usually English)
                sim1 = fuzz.ratio(title.lower(), search_matched_name.lower()) / 100.0
                sim2 = fuzz.ratio(title.lower(), original_name.lower()) / 100.0
                localized_sim = fuzz.ratio(title.lower(), details.get("name", "").lower()) / 100.0
                
                # Check fuzzy match against all alternative titles
                best_alt_sim = 0.0
                alt_titles = details.get("alternative_titles", {}).get("results", [])
                for alt in alt_titles:
                    alt_sim = fuzz.ratio(title.lower(), alt.get("title", "").lower()) / 100.0
                    if alt_sim > best_alt_sim:
                        best_alt_sim = alt_sim
                        
                # If we get a very high match on an alternative title (like Romaji), boost it significantly!
                if best_alt_sim > 0.85:
                    best_alt_sim = 0.95
                    
                base_conf = max(sim1, sim2, localized_sim, best_alt_sim) * 0.7
                if base_conf > 0.6:  # Uncap it a bit if it was a strong alias match
                    base_conf = max(base_conf, best_alt_sim)
                
                # Check if the title matches a specific season name better
                matched_season = None
                best_season_sim = 0.0

                all_seasons = details.get("seasons", []) + details_en.get("seasons", [])
                season_names = {
                    season["season_number"]: season["name"]
                    for season in details_en.get("seasons", [])
                    if isinstance(season.get("season_number"), int)
                    and season["season_number"] > 0 and season.get("name")
                }
                for season in details.get("seasons", []):
                    number, name = season.get("season_number"), season.get("name")
                    if isinstance(number, int) and number > 0 and name and (
                        number not in season_names or not re.fullmatch(r"(?i:season)\s*\d+|第\s*[一二三四五六七八九十\d]+\s*季", name)
                    ):
                        season_names[number] = name

                for season in all_seasons:
                    s_name = season.get("name", "")
                    s_num = season.get("season_number", 0)
                    if s_num == 0 or not s_name:  # Skip Specials
                        continue
                    s_sim_ratio = fuzz.ratio(title.lower(), s_name.lower()) / 100.0
                    s_sim_token = fuzz.token_set_ratio(title.lower(), s_name.lower()) / 100.0
                    s_sim = max(s_sim_ratio, s_sim_token)

                    if len(s_name) > 4:
                        s_sim_partial = fuzz.partial_ratio(title.lower(), s_name.lower()) / 100.0
                        s_sim = max(s_sim, s_sim_partial)

                    if s_sim > best_season_sim and s_sim > 0.8:
                        best_season_sim = s_sim
                        matched_season = s_num
                        
                if best_season_sim > best_alt_sim:
                    best_alt_sim = best_season_sim
                    base_conf = max(base_conf, best_alt_sim)

                boost = 0.0
                if item.get("origin_country") and "JP" in item.get("origin_country"):
                    boost += 0.1
                if 16 in item.get("genre_ids", []):
                    boost += 0.1
                    
                conf = min(1.0, base_conf + boost)
                
                results.append(TmdbMatch(
                    tmdb_id=tmdb_id,
                    name=final_name,
                    original_name=original_name,
                    season_count=season_count,
                    confidence=conf,
                    matched_season=matched_season,
                    season_names=season_names,
                    backdrop_path=item.get("backdrop_path") or details.get("backdrop_path"),
                ))
            return results
        except Exception as e:
            print(f"TMDB search error ({language}): {type(e).__name__}")
            return []

    async def verify_episode(self, tmdb_id: int, season: int, episode: int) -> bool:
        if not self.api_key:
            return False

        client = self._get_client()
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
