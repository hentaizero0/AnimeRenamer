import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.config import AppConfig, SeriesDB
from backend.domain.naming import compute_target_plan
from backend.models import BatchTriageJob, FileTriageItem, SeriesConfig, TriageStatus
from backend.parser import parse_file
from backend.services.queue_service import QueueService
from backend.tmdb import TmdbClient, TmdbMatch
from backend.watcher import DownloadDirHandler, process_directory, tmdb_async_resolve


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,filename,episodes,tmdb_id,title,matched_season,expected_season",
    [
        ("Vinland Saga", "Vinland Saga S02E{ep:02d}-[1080p][BDRIP][x265.FLAC].mkv", range(1, 25), 88803, "冰海战记", None, 2),
        ("Vinland Saga", "[BeanSub] Vinland Saga - {ep:02d} [WebRip 1080p HEVC AAC].mkv", range(1, 25), 88803, "冰海战记", None, 1),
        ("Spy x Family", "[Sakurato] Spy x Family S3 [{ep:02d}][HEVC-10bit 1080p AAC].mkv", range(1, 14), 120089, "间谍过家家", None, 3),
        ("Steel Ball Run：JoJo no Kimyou na Bouken", "[Sakurato] Steel Ball Run：JoJo no Kimyou na Bouken [{ep:02d}][HEVC-10bit 1080p AAC].mkv", range(1, 3), 45790, "JOJO的奇妙冒险", 6, 6),
        ("Re Zero kara Hajimeru Isekai Seikatsu", "[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][{ep:02d}][BDRip 1080p AVC AAC][CHS].mp4", range(26, 51), 65942, "Re：从零开始的异世界生活", None, 1),
    ],
)
async def test_resolved_season_paths_keep_numbering(
    monkeypatch, query, filename, episodes, tmdb_id, title, matched_season, expected_season
):
    names = [filename.format(ep=ep) for ep in episodes]
    items = [FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name)) for name in names]
    job = BatchTriageJob(id="fixture", source_dir="Show", items=items)
    queue = QueueService()
    queue.put(job)
    config = AppConfig(_env_file=None, download_dir="/fixture/input", storage_dir="/fixture/output")

    async def search(_self, _title):
        return [TmdbMatch(tmdb_id, title, query, 6, 1.0, matched_season)]

    monkeypatch.setattr(TmdbClient, "search_anime", search)
    await tmdb_async_resolve(job.id, query, ".", config, queue, key_resolver=lambda: "fixture-key")

    assert job.series_config.tmdb_id == tmdb_id
    assert job.effective_title == title
    assert job.effective_season == expected_season
    for item, episode in zip(items, episodes):
        assert item.parsed.episode == episode
        plan = compute_target_plan(job, item, config, {episode: [Path(item.relative_path).stem]})
        expected = f"{title} S{expected_season:02d}E{episode:02d}{Path(item.relative_path).suffix}"
        assert plan.target_file == Path(config.storage_dir) / title / f"Season {expected_season:02d}" / expected


def test_manual_season_configuration_precedes_parsed_season():
    name = "Show S02E01.mkv"
    item = FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name))
    job = BatchTriageJob(
        id="manual", source_dir="Show", items=[item],
        series_config=SeriesConfig(tmdb_name="Show", season=4),
    )
    assert job.effective_season == 4
    job.override_season = 5
    assert job.effective_season == 5


@pytest.mark.asyncio
async def test_tmdb_result_does_not_replace_manual_series_config(monkeypatch):
    name = "Show S02E01.mkv"
    item = FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name))
    manual = SeriesConfig(tmdb_name="Manual Show", season=4)
    job = BatchTriageJob(id="manual", source_dir="Show", items=[item], series_config=manual)
    queue = QueueService()
    queue.put(job)

    async def search(_self, _title):
        return [TmdbMatch(123, "TMDB Show", "Show", 4, 1.0)]

    monkeypatch.setattr(TmdbClient, "search_anime", search)
    await tmdb_async_resolve(job.id, "Show", ".", AppConfig(_env_file=None), queue, key_resolver=lambda: "fixture-key")
    assert job.series_config is manual
    assert job.effective_title == "Manual Show"
    assert job.effective_season == 4


@pytest.mark.parametrize("episode", [17, 18, 19, 22, 23])
def test_uma_romaji_release_metadata_is_removed(episode):
    name = f"Uma Musume Shinderera Gurei 2025 S01E{episode}-[1080p][BDRIP][x265.OPUS].mkv"
    parsed = parse_file(name)
    assert (parsed.detected_title, parsed.season, parsed.episode) == (
        "Uma Musume Shinderera Gurei", 1, episode,
    )


def test_uma_english_and_title_year_controls():
    english = parse_file("[LoliHouse] Uma Musume Cinderella Gray - 01 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv")
    assert (english.detected_title, english.episode) == ("Uma Musume Cinderella Gray", 1)
    assert parse_file("Show (2025) S01E01-[x265.OPUS].mkv").detected_title == "Show (2025)"
    assert parse_file("Show 2025 Edition S01E01-[x265.OPUS].mkv").detected_title == "Show 2025 Edition"
    assert parse_file("Show II (2025) - 01.mkv").detected_title == "Show (2025)"
    bracket_year = parse_file("Show S01 [2025]")
    assert (bracket_year.detected_title, bracket_year.episode) == ("Show [2025]", None)


def test_rezero_end_marker_keeps_tmdb_default_episode_number():
    first = parse_file("[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26][BDRip 1080p AVC AAC][CHS].mp4")
    last = parse_file("[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][50END][BDRip 1080p AVC AAC][CHS].mp4")
    assert (first.season, first.episode, last.season, last.episode) == (None, 26, None, 50)


@pytest.mark.asyncio
async def test_directory_fallback_uses_title_not_release_group(monkeypatch):
    name = "Unknown S01E17.mkv"
    item = FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name))
    job = BatchTriageJob(id="directory", source_dir="Show", items=[item])
    queue = QueueService()
    queue.put(job)
    queries = []

    async def search(_self, title):
        queries.append(title)
        if title == "Uma Musume Shinderera Gurei":
            return [TmdbMatch(262700, "赛马娘 芦毛灰姑娘", title, 1, 1.0)]
        return []

    monkeypatch.setattr(TmdbClient, "search_anime", search)
    await tmdb_async_resolve(
        job.id, "Unknown", "[BDrip] Uma Musume Shinderera Gurei S01 [7³ACG]",
        AppConfig(_env_file=None), queue, key_resolver=lambda: "fixture-key",
    )
    assert queries == ["Unknown", "Uma Musume Shinderera Gurei"]
    assert job.series_config.tmdb_id == 262700
    assert job.effective_season == 1


@pytest.mark.asyncio
async def test_directory_fallback_keeps_bracketed_title_year(monkeypatch):
    item = FileTriageItem(relative_path="Unknown S01E01.mkv", is_video=True, parsed=parse_file("Unknown S01E01.mkv"))
    job = BatchTriageJob(id="year", source_dir="Show", items=[item])
    queue = QueueService()
    queue.put(job)
    queries = []

    async def search(_self, title):
        queries.append(title)
        return []

    monkeypatch.setattr(TmdbClient, "search_anime", search)
    await tmdb_async_resolve(job.id, "Unknown", "Show S01 [2025]", AppConfig(_env_file=None), queue, key_resolver=lambda: "fixture-key")
    assert queries == ["Unknown", "Show [2025]"]


@pytest.mark.asyncio
async def test_baha_titles_use_localized_tmdb_name_and_keep_candidate_ranking(monkeypatch):
    names = [f"穹廬下的魔女 [Baha] S01E{ep:02d}.mp4" for ep in range(1, 13)]
    items = [FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name)) for name in names]
    assert all(item.parsed.detected_title == "穹廬下的魔女" for item in items)
    leading = parse_file("[Baha] 穹廬下的魔女 S01E01.mp4")
    assert (leading.detected_title, leading.fansub_group) == ("穹廬下的魔女", "")

    class Response:
        status_code = 200

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

        def raise_for_status(self):
            pass

    class FixedTmdb:
        async def get(self, url, *, params, **_kwargs):
            if url.endswith("/search/tv"):
                return Response({"results": [
                    {"id": 999, "name": "Other Witch", "original_name": "別の魔女", "origin_country": ["JP"], "genre_ids": [16]},
                    {"id": 288971, "name": "The Witch in the Dome", "original_name": "魔女", "origin_country": ["JP"], "genre_ids": [16]},
                ]})
            tmdb_id = int(url.rsplit("/", 1)[-1])
            localized = tmdb_id == 288971
            name = ("穹庐下的魔女" if localized else "穹庐下的魔法") if params.get("language") else "English title"
            return Response({"name": name, "number_of_seasons": 1, "seasons": [], "alternative_titles": {"results": []}})

    monkeypatch.setattr(TmdbClient, "_get_client", lambda _self: FixedTmdb())
    client = TmdbClient("fixture-key")
    simplified = await client.search_anime("穹庐下的魔女")
    assert simplified[0].tmdb_id == 288971
    assert simplified[0].confidence > 0.6
    assert simplified[0].confidence > simplified[1].confidence

    job = BatchTriageJob(id="baha", source_dir="Show", items=items)
    queue = QueueService()
    queue.put(job)
    config = AppConfig(_env_file=None, download_dir="/fixture/input", storage_dir="/fixture/output")
    await tmdb_async_resolve(job.id, items[0].parsed.detected_title, ".", config, queue, key_resolver=lambda: "fixture-key")
    assert job.series_config.tmdb_id == 288971
    assert job.effective_title == "穹庐下的魔女"
    for item, episode in zip(items, range(1, 13)):
        plan = compute_target_plan(job, item, config)
        assert plan.target_file == Path(config.storage_dir) / "穹庐下的魔女" / "Season 01" / f"穹庐下的魔女 S01E{episode:02d}.mp4"


@pytest.mark.asyncio
@pytest.mark.parametrize("localized_season,expected_title", [
    ("飙马野郎篇", "飙马野郎篇"),
    ("Season 6", "STEEL BALL RUN"),
])
async def test_jojo_candidates_keep_series_and_season_titles_separate(monkeypatch, localized_season, expected_title):
    async def get(url, *, params, **_kwargs):
        if url.endswith("/search/tv"):
            data = {"results": [
                {"id": 336466, "name": "Steel Ball Run", "original_name": "Steel Ball Run", "origin_country": [], "genre_ids": []},
                {"id": 60862, "name": "JoJo OVA", "original_name": "ジョジョOVA", "origin_country": ["JP"], "genre_ids": [16]},
                {"id": 45790, "name": "JoJo's Bizarre Adventure", "original_name": "ジョジョの奇妙な冒険", "origin_country": ["JP"], "genre_ids": [16]},
            ]}
        else:
            tmdb_id = int(url.rsplit("/", 1)[-1])
            data = {
                "name": "JOJO的奇妙冒险" if tmdb_id == 45790 and params.get("language") else "JoJo",
                "number_of_seasons": 6 if tmdb_id == 45790 else 1,
                "seasons": ([{"name": localized_season, "season_number": 6}] if params.get("language") else [{"name": "STEEL BALL RUN", "season_number": 6}]) if tmdb_id == 45790 else [],
                "alternative_titles": {"results": []},
            }
        return SimpleNamespace(status_code=200, json=lambda: data, raise_for_status=lambda: None)

    http = SimpleNamespace(get=AsyncMock(side_effect=get))
    monkeypatch.setattr(TmdbClient, "_get_client", lambda _self: http)
    matches = await TmdbClient("fixture-key").search_anime("Steel Ball Run：JoJo no Kimyou na Bouken")
    assert matches[0].tmdb_id == 45790
    assert (matches[0].name, matches[0].matched_season) == ("JOJO的奇妙冒险", 6)
    assert matches[0].season_names[6] == expected_title
    assert matches[0].name != "飆馬野郎"


@pytest.mark.asyncio
async def test_tmdb_season_title_and_link_metadata_reach_pending_and_preview(monkeypatch, tmp_path):
    import backend.main as main_api

    config = AppConfig(_env_file=None, download_dir=tmp_path / "input", storage_dir=tmp_path / "output")
    queue = QueueService()
    names = [f"[Sakurato] Steel Ball Run：JoJo no Kimyou na Bouken [{ep:02d}].mkv" for ep in (1, 2)]
    job = BatchTriageJob(
        id="jojo-details", source_dir="JoJo",
        items=[FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name)) for name in names],
    )
    queue.put(job)

    async def search(_self, _title):
        return [TmdbMatch(45790, "JOJO的奇妙冒险", "ジョジョの奇妙な冒険", 6, 1.0, 6, {6: "飙马野郎篇"})]

    monkeypatch.setattr(TmdbClient, "search_anime", search)
    await tmdb_async_resolve(job.id, "Steel Ball Run：JoJo no Kimyou na Bouken", ".", config, queue, key_resolver=lambda: "fixture-key")
    monkeypatch.setattr(main_api, "queue", queue.queue)
    monkeypatch.setattr(main_api, "config", config)
    card = (await main_api.get_queue())[0]
    preview = await main_api.preview_job(job.id)
    assert (card["tmdb_id"], card["season_title"], card["season"], card["video_count"]) == (45790, "飙马野郎篇", 6, 2)
    assert (preview["tmdb_id"], preview["season_title"], preview["season"]) == (45790, "飙马野郎篇", 6)

    job.override_season = 5
    assert job.effective_season_title is None

    manual = BatchTriageJob(
        id="manual-details", source_dir="Manual", items=[FileTriageItem(relative_path="Manual S02E01.mkv", is_video=True, parsed=parse_file("Manual S02E01.mkv"))],
        series_config=SeriesConfig(tmdb_name="冰海战记", tmdb_id=88803, season=2),
    )
    queue.put(manual)
    manual_card = next(item for item in await main_api.get_queue() if item["id"] == manual.id)
    manual_preview = await main_api.preview_job(manual.id)
    assert manual_card["tmdb_id"] == manual_preview["tmdb_id"] == 88803
    assert manual_card["season_title"] is None


@pytest.mark.asyncio
async def test_uma_english_and_romaji_queries_match_same_tmdb_id(monkeypatch):
    async def get(url, *, params, **_kwargs):
        if url.endswith("/search/tv"):
            data = {"results": [{
                "id": 262700, "name": "Uma Musume Cinderella Gray", "original_name": "ウマ娘 シンデレラグレイ",
                "origin_country": ["JP"], "genre_ids": [16],
            }]}
        else:
            data = {
                "name": "赛马娘 芦毛灰姑娘" if params.get("language") else "Uma Musume Cinderella Gray",
                "number_of_seasons": 1, "seasons": [],
                "alternative_titles": {"results": [{"title": "Uma Musume Shinderera Gurei"}]},
            }
        return SimpleNamespace(status_code=200, json=lambda: data, raise_for_status=lambda: None)

    http = SimpleNamespace(get=AsyncMock(side_effect=get))
    monkeypatch.setattr(TmdbClient, "_get_client", lambda _self: http)
    client = TmdbClient("fixture-key")
    romaji = await client.search_anime(parse_file("Uma Musume Shinderera Gurei 2025 S01E17-[1080p][BDRIP][x265.OPUS].mkv").detected_title)
    english = await client.search_anime(parse_file("[LoliHouse] Uma Musume Cinderella Gray - 01 [WebRip 1080p HEVC AAC].mkv").detected_title)
    assert (romaji[0].tmdb_id, english[0].tmdb_id) == (262700, 262700)
    assert romaji[0].confidence > 0.6 and english[0].confidence > 0.6


def test_refresh_preserves_manual_title_season_and_episode(monkeypatch):
    config = AppConfig(_env_file=None, download_dir="/fixture/input")
    queue = QueueService()
    item = FileTriageItem(relative_path="Show/Show S01E01.mkv", is_video=True, parsed=parse_file("Show S01E01.mkv"))
    current = BatchTriageJob(
        id="refresh", source_dir="Show", items=[item],
        series_config=SeriesConfig(tmdb_name="Configured Show", season=1),
        override_title="My Show", override_season=3, override_episode=7,
    )
    queue.put(current)
    refreshed = BatchTriageJob(id="new", source_dir="Show", items=[item.model_copy(deep=True)])
    monkeypatch.setattr("backend.watcher.resolve_anime_dir_and_mode", lambda *_args: (Path("/fixture/input/Show"), "confirm"))
    monkeypatch.setattr("backend.watcher.process_directory", lambda *_args, **_kwargs: refreshed)
    handler = DownloadDirHandler(config, MagicMock(), MagicMock(), queue_service=queue)
    handler.process_dir_event(Path("/fixture/input/Show"))
    latest = queue.get("refresh")
    assert latest is refreshed
    assert (latest.override_title, latest.override_season, latest.override_episode) == ("My Show", 3, 7)
    assert (latest.effective_title, latest.effective_season) == ("My Show", 3)


@pytest.mark.asyncio
async def test_tmdb_completion_keeps_newer_manual_edits(monkeypatch):
    queue = QueueService()
    item = FileTriageItem(relative_path="Show S01E01.mkv", is_video=True, parsed=parse_file("Show S01E01.mkv"))
    job = BatchTriageJob(id="race", source_dir="Show", items=[item])
    queue.put(job)
    started = asyncio.Event()
    release = asyncio.Event()

    async def search(_self, _title):
        started.set()
        await release.wait()
        return [TmdbMatch(1, "TMDB Show", "Show", 1, 1.0)]

    monkeypatch.setattr(TmdbClient, "search_anime", search)
    task = asyncio.create_task(tmdb_async_resolve(job.id, "Show", ".", AppConfig(_env_file=None), queue, key_resolver=lambda: "fixture-key"))
    await started.wait()
    job.override_title = "My Show"
    job.override_season = 4
    job.override_episode = 8
    release.set()
    await task
    assert (job.override_title, job.override_season, job.override_episode) == ("My Show", 4, 8)
    assert (job.effective_title, job.effective_season) == ("My Show", 4)


@pytest.mark.asyncio
async def test_stale_tmdb_result_does_not_modify_refreshed_job(monkeypatch):
    queue = QueueService()
    item = FileTriageItem(relative_path="Show S01E01.mkv", is_video=True, parsed=parse_file("Show S01E01.mkv"))
    old = BatchTriageJob(id="stale", source_dir="Show", items=[item])
    queue.put(old)
    started = asyncio.Event()
    release = asyncio.Event()

    async def search(_self, _title):
        started.set()
        await release.wait()
        return [TmdbMatch(1, "Old TMDB Show", "Show", 1, 1.0)]

    monkeypatch.setattr(TmdbClient, "search_anime", search)
    task = asyncio.create_task(tmdb_async_resolve(old.id, "Show", ".", AppConfig(_env_file=None), queue, key_resolver=lambda: "fixture-key"))
    await started.wait()
    refreshed = BatchTriageJob(id=old.id, source_dir="Show", items=[item.model_copy(deep=True)])
    queue.put(refreshed)
    release.set()
    await task
    assert refreshed.series_config is None
    assert refreshed.override_title is None


@pytest.mark.asyncio
async def test_conflicting_tmdb_season_never_reaches_auto_executor(monkeypatch):
    queue = QueueService()
    name = "Show S02E01.mkv"
    item = FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name))
    job = BatchTriageJob(id="conflict", source_dir="Show", items=[item], default_mode="auto")
    queue.put(job)

    async def search(_self, _title):
        return [TmdbMatch(1, "Show", "Show", 6, 1.0, 6)]

    executor = AsyncMock()
    monkeypatch.setattr(TmdbClient, "search_anime", search)
    monkeypatch.setattr("backend.triage.execute_triage_job", executor)
    handler = DownloadDirHandler(AppConfig(_env_file=None, default_mode="auto", tmdb_api_key="fixture-key"), MagicMock(), MagicMock(), queue_service=queue)
    await handler._tmdb_then_auto(job)
    assert job.series_config.mode == "confirm"
    assert job.effective_season == 2
    executor.assert_not_awaited()


def test_mixed_season_batch_is_held_before_planning(tmp_path):
    download = tmp_path / "downloads"
    show = download / "Show"
    for season in (1, 2):
        folder = show / f"Season {season}"
        folder.mkdir(parents=True)
        (folder / f"Show S{season:02d}E01.mkv").write_bytes(b"fixture")
    config = AppConfig(_env_file=None, download_dir=download, storage_dir=tmp_path / "output")
    job = process_directory(show, config, SeriesDB(tmp_path / "empty.yaml"))
    assert job is not None
    assert job.has_conflict is False
    assert job.status == TriageStatus.ignored
    assert job.ignore_reason == "mixed_seasons"
    with pytest.raises(ValueError, match="mixed seasons"):
        compute_target_plan(job, job.items[0], config)


def test_same_episode_still_conflicts_when_only_one_file_has_a_season():
    items = [
        FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name))
        for name in ("Show S01E01.mkv", "Show - 01.mkv")
    ]
    job = BatchTriageJob(id="duplicate", source_dir="Show", items=items, series_config=SeriesConfig(tmdb_name="Show", season=2))
    assert job.has_mixed_seasons is False
    assert job.has_conflict is True
