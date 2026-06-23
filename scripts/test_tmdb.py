import asyncio, httpx, json
import os

API_KEY = os.environ.get("TMDB_API_KEY", "")

async def main():
    if not API_KEY:
        raise SystemExit("Set TMDB_API_KEY before running this script.")
    async with httpx.AsyncClient() as client:
        # Search WITHOUT language
        resp = await client.get("https://api.themoviedb.org/3/search/tv", params={"api_key": API_KEY, "query": "Chainsaw Man - The Compilation"})
        items = resp.json().get("results", [])
        if not items:
            print("No items found")
            return
            
        item = items[0]
        matched_name = item.get("name")
        print("Matched name (no language):", matched_name)
        
        # Details WITH language
        d_resp = await client.get(f"https://api.themoviedb.org/3/tv/{item['id']}", params={"api_key": API_KEY, "language": "zh-CN"})
        details = d_resp.json()
        print("Final Chinese name:", details.get("name"))

asyncio.run(main())
