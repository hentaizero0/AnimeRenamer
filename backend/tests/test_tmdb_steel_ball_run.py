import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.tmdb import TmdbClient, TmdbMatch

@pytest.mark.asyncio
async def test_tmdb_season_matching_steel_ball_run():
    client = TmdbClient(api_key="fake_key")

    mock_httpx_client = MagicMock()

    # Mock for /search/tv
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "id": 45790,
                "name": "JoJo's Bizarre Adventure",
                "original_name": "ジョジョの奇妙な冒険",
                "origin_country": ["JP"],
                "genre_ids": [16]
            }
        ]
    }

    # Mock for /tv/45790
    mock_details_resp = MagicMock()
    mock_details_resp.status_code = 200
    mock_details_resp.json.return_value = {
        "name": "JOJO的奇妙冒险",
        "number_of_seasons": 6,
        "seasons": [
            {"name": "Season 1", "season_number": 1},
            {"name": "Season 2", "season_number": 2},
            {"name": "Season 3", "season_number": 3},
            {"name": "Season 4", "season_number": 4},
            {"name": "Season 5", "season_number": 5},
            {"name": "飙马野郎", "season_number": 6} # Sometimes localized
        ],
        "alternative_titles": {
            "results": [
                {"title": "JoJo no Kimyou na Bouken"}
            ]
        }
    }

    # Second case: season named "Steel Ball Run"
    mock_details_resp_en = MagicMock()
    mock_details_resp_en.status_code = 200
    mock_details_resp_en.json.return_value = {
        "name": "JOJO的奇妙冒险",
        "number_of_seasons": 6,
        "seasons": [
            {"name": "Season 1", "season_number": 1},
            {"name": "Steel Ball Run", "season_number": 6}
        ],
        "alternative_titles": {
            "results": [
                {"title": "JoJo no Kimyou na Bouken"}
            ]
        }
    }

    async def mock_get(url, *args, **kwargs):
        if "search/tv" in url:
            return mock_search_resp
        elif "tv/45790" in url:
            # We'll use the english season name for testing the partial match
            return mock_details_resp_en
        return MagicMock(status_code=404)

    mock_httpx_client.get = AsyncMock(side_effect=mock_get)

    title = "Steel Ball Run：JoJo no Kimyou na Bouken"

    results = await client._search_once(mock_httpx_client, title, language="zh-CN")

    assert len(results) == 1
    match = results[0]

    assert match.name == "JOJO的奇妙冒险"
    assert match.matched_season == 6
    assert match.confidence > 0.8  # Should be high confident match
