"""
test_plan_acceptance.py — Plan 验收测试套件

每个测试对应 plan.md 里的一条修复任务（A1/A2/A3/B1/B2/B3/C1/C2/C3）。
- 修复前：对应测试为 RED（证明 bug 真实存在）。
- 按 plan 修复后：对应测试转 GREEN（即视为该条验收通过）。

跑法：
    python -m pytest backend/tests/test_plan_acceptance.py -v

命名约定 test_<planid>_<desc>，方便逐条对账。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
import yaml

from backend.config import AppConfig, SeriesDB
from backend.models import BatchTriageJob, FileTriageItem, ParsedAnime, TriageStatus, SeriesConfig
from backend.triage import execute_triage_job
from backend.watcher import process_directory
from backend import tmdb as tmdb_mod

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 公共 fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def dirs(tmp_path):
    download_dir = tmp_path / "downloads"
    storage_dir = tmp_path / "storage"
    airing_dir = tmp_path / "airing"
    collect_dir = tmp_path / "collect"
    for d in (download_dir, storage_dir, airing_dir, collect_dir):
        d.mkdir()
    config = AppConfig(
        download_dir=str(download_dir),
        storage_dir=str(storage_dir),
        jellyfin_airing_dir=str(airing_dir),
        jellyfin_collect_dir=str(collect_dir),
        default_mode="confirm",
    )
    return download_dir, storage_dir, airing_dir, collect_dir, config


def _mk_video(download_dir: Path, rel: str, title: str, episode: int | None,
              season: int = 1, is_video: bool = True) -> FileTriageItem:
    src = download_dir / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("data")
    parsed = ParsedAnime(
        raw_filename=Path(rel).name,
        detected_title=title,
        season=season,
        episode=episode,
        extension=Path(rel).suffix.lstrip("."),
        confidence=0.9,
    )
    return FileTriageItem(relative_path=rel, parsed=parsed, is_video=is_video)


# ===========================================================================
# A1 — triage.py: executed_moves 未定义 / 回滚机制
# ===========================================================================
class TestA1ExecutedMovesRollback:
    """plan A1: confirm 模式成功移动后必须能记录并在后续失败时回滚。"""

    @pytest.mark.asyncio
    async def test_a1_confirm_success_no_nameerror(self, dirs):
        # 修复前：第一次成功 move 后 executed_moves.append → NameError
        download_dir, storage_dir, *_, config = dirs
        item = _mk_video(download_dir, "Frieren/Frieren - 01.mkv", "Frieren", 1)
        job = BatchTriageJob(id="a1a", source_dir="Frieren", items=[item])

        res = await execute_triage_job(job, config, dry_run=False)

        assert res.success is True
        assert (storage_dir / "Frieren" / "Season 01" / "Frieren S01E01.mkv").exists()

    @pytest.mark.asyncio
    async def test_a1_rollback_on_later_failure(self, dirs):
        """前一个文件成功、后一个失败时，已成功的文件必须被回滚回原位。"""
        download_dir, storage_dir, *_, config = dirs
        # ep1 正常；ep2 的目标已存在 → rename 失败 → 触发回滚 ep1
        ok = _mk_video(download_dir, "S/S - 01.mkv", "S", 1)
        bad = _mk_video(download_dir, "S/S - 02.mkv", "S", 2)
        job = BatchTriageJob(id="a1b", source_dir="S", items=[ok, bad])

        # 预先占位 ep2 目标，制造冲突
        clash = storage_dir / "S" / "Season 01" / "S S01E02.mkv"
        clash.parent.mkdir(parents=True, exist_ok=True)
        clash.write_text("existing")

        res = await execute_triage_job(job, config, dry_run=False)

        assert res.success is False
        # ep1 已被回滚：原始下载位置应仍在，storage 不应残留 ep1
        assert (download_dir / "S/S - 01.mkv").exists()
        assert not (storage_dir / "S" / "Season 01" / "S S01E01.mkv").exists()


# ===========================================================================
# A2 — triage.py: 无集数分支 res 未定义 + 缩进错乱
# ===========================================================================
class TestA2NoEpisodeBranch:
    """plan A2: 无集数文件在 auto / confirm 两种模式下都不能崩。"""

    @pytest.mark.asyncio
    async def test_a2_confirm_no_episode_moves_to_season(self, dirs):
        download_dir, storage_dir, *_, config = dirs
        # 无 episode 的视频（电影/特典）
        item = _mk_video(download_dir, "Movie/extra.mkv", "Movie", None)
        item.parsed = ParsedAnime(raw_filename="extra.mkv", detected_title="", season=None,
                                  episode=None, extension="mkv", confidence=0.3)
        job = BatchTriageJob(id="a2a", source_dir="Movie", items=[item],
                             override_title="MovieTitle")

        res = await execute_triage_job(job, config, dry_run=False)

        assert res.success is True
        assert (storage_dir / "MovieTitle" / "Season 01" / "extra.mkv").exists()

    @pytest.mark.asyncio
    async def test_a2_auto_no_episode_keeps_in_place(self, dirs):
        download_dir, *_, config = dirs
        item = _mk_video(download_dir, "Auto/extra.mkv", "", None)
        item.parsed = ParsedAnime(raw_filename="extra.mkv", detected_title="", season=None,
                                  episode=None, extension="mkv", confidence=0.3)
        job = BatchTriageJob(id="a2b", source_dir="Auto", items=[item],
                             override_title="AutoTitle", default_mode="auto")

        # 修复前：auto 分支读取未定义的 res → NameError
        res = await execute_triage_job(job, config, dry_run=False)

        assert res.success is True
        # auto 模式无集数文件原地保留
        assert (download_dir / "Auto/extra.mkv").exists()


# ===========================================================================
# A3 — watcher.py: uuid 未 import（no_video 路径崩溃）
# ===========================================================================
class TestA3UuidImport:
    """plan A3: 扫描到无视频目录时返回 ignored job，不能 NameError。"""

    def test_a3_no_video_dir_returns_ignored(self, tmp_path):
        class DummyConfig:
            download_dir = str(tmp_path)

        anime = tmp_path / "NoVideo"
        anime.mkdir()
        (anime / "readme.txt").write_text("info")
        (anime / "cover.jpg").write_text("img")

        # 修复前：id=str(uuid.uuid4()...) → NameError: name 'uuid' is not defined
        job = process_directory(anime, DummyConfig(), None)

        assert job is not None
        assert job.status == TriageStatus.ignored
        assert job.ignore_reason == "no_video"
        assert job.id  # id 必须被成功赋值（非空）


# ===========================================================================
# B1 — override_episode 存了却从不生效
# ===========================================================================
class TestB1OverrideEpisode:
    """plan B1: 用户手动指定 override_episode 后，单视频 job 输出文件名应使用该集号。

    语义（单视频场景，A/B 两种解释都满足）：override_episode 强制该视频的集号。
    """

    @pytest.mark.asyncio
    async def test_b1_override_episode_applied(self, dirs):
        download_dir, storage_dir, *_, config = dirs
        # 解析出来是 ep1，但用户手动覆盖为 ep5
        item = _mk_video(download_dir, "X/X - 01.mkv", "X", 1)
        job = BatchTriageJob(id="b1", source_dir="X", items=[item],
                             override_title="X", override_episode=5)

        res = await execute_triage_job(job, config, dry_run=False)

        assert res.success is True
        # 修复前：override_episode 被忽略，输出 S01E01
        assert (storage_dir / "X" / "Season 01" / "X S01E05.mkv").exists()
        assert not (storage_dir / "X" / "Season 01" / "X S01E01.mkv").exists()


# ===========================================================================
# B2 — config.py: SeriesDB.save() 用 exclude_unset 丢字段
# ===========================================================================
class TestB2SeriesPersistence:
    """plan B2: 存盘必须保留 mode/season 等带默认值的字段（改用 exclude_none）。"""

    def test_b2_default_fields_persisted_to_yaml(self, tmp_path):
        cfg_path = tmp_path / "series_config.yaml"
        db = SeriesDB(cfg_path)
        # 用 model_validate 构造：mode/season 未显式设置（取默认值，但 unset 标记为真）
        sc = SeriesConfig.model_validate({"tmdb_name": "Frieren"})
        db.add(sc, title="Frieren")

        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        entry = raw["series"]["Frieren"]

        # 修复前：exclude_unset=True → 'mode'/'season' 不会被写进 yaml
        assert "mode" in entry, "mode 默认值应被持久化"
        assert "season" in entry, "season 默认值应被持久化"
        assert entry["mode"] == "confirm"
        assert entry["season"] == 1

    def test_b2_reload_roundtrip_stable(self, tmp_path):
        cfg_path = tmp_path / "series_config.yaml"
        db = SeriesDB(cfg_path)
        db.add(SeriesConfig.model_validate({"tmdb_name": "Bocchi"}), title="Bocchi")

        db2 = SeriesDB(cfg_path)
        got = db2.get("Bocchi")
        assert got is not None
        assert got.mode == "confirm"
        assert got.season == 1


# ===========================================================================
# B3 — tmdb.py: search_anime 收了 season 参数却从不使用
# ===========================================================================
class TestB3SearchSignature:
    """plan B3: 删除 search_anime 未使用的 season 参数（消除误导）。"""

    def test_b3_season_param_removed(self):
        params = inspect.signature(tmdb_mod.TmdbClient.search_anime).parameters
        # 修复前：'season' 在签名里但函数体从不使用
        assert "season" not in params, "未使用的 season 参数应当删除"

    @pytest.mark.asyncio
    async def test_b3_empty_key_returns_empty(self):
        # 行为回归保护：无 key 时返回空列表，不发请求
        client = tmdb_mod.TmdbClient(api_key="")
        assert await client.search_anime("anything") == []


# ===========================================================================
# C1 — main.py: 删死代码（不可达 return / if False）
# ===========================================================================
class TestC1MainDeadCode:
    """plan C1: 删除 main.py 中的不可达 return 和 if False 死块。"""

    def _src(self) -> str:
        return (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")

    def test_c1a_no_unreachable_return_series(self):
        src = self._src()
        assert "return series_db._series" not in src, "不可达的 return 应删除"

    def test_c1b_no_if_false_block(self):
        src = self._src()
        assert "if False:" not in src, "if False 死块应删除"


# ===========================================================================
# C2 — parser.py: 删未使用符号
# ===========================================================================
class TestC2ParserDeadCode:
    """plan C2: 删除 parser.py 中未使用的 _ParseState / _TRAILING_TITLE_DIGIT_RE。"""

    def _src(self) -> str:
        return (REPO_ROOT / "backend" / "parser.py").read_text(encoding="utf-8")

    def test_c2a_parsestate_removed(self):
        assert "_ParseState" not in self._src(), "未使用的 _ParseState 应删除"

    def test_c2b_trailing_digit_const_removed(self):
        assert "_TRAILING_TITLE_DIGIT_RE" not in self._src(), \
            "未使用的 _TRAILING_TITLE_DIGIT_RE 应删除"

    def test_c2c_parser_still_works(self):
        # 回归保护：删死代码后解析功能必须不变
        from backend.parser import parse_file
        p = parse_file("[SubsPlease] Dungeon Meshi - 15 (1080p) [ABC123].mkv")
        assert p.episode == 15
        assert "Dungeon Meshi" in p.detected_title


# ===========================================================================
# C3 — 仓库根目录：reset_env.py 重复
# ===========================================================================
class TestC3DuplicateFiles:
    """plan C3: reset_env.py 只应保留一份（scripts/ 下）。"""

    def test_c3_single_reset_env(self):
        root_copy = REPO_ROOT / "reset_env.py"
        scripts_copy = REPO_ROOT / "scripts" / "reset_env.py"
        assert scripts_copy.exists(), "scripts/reset_env.py 应保留"
        # 修复前：根目录还存在一份完全相同的副本
        assert not root_copy.exists(), "根目录重复的 reset_env.py 应删除"
