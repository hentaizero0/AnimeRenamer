"""
test_tmdb_key_flow.py — TMDB API Key 全链路验收测试（plan Part 1 · 阶段 E）

覆盖三段 bug 的修复目标：
  ① 前端"掩码回灌"自毁  → 服务端永不回吐可用 key + POST 防覆盖/防掩码。
  ② config 单例陈旧      → 引入 get_effective_tmdb_key() 单一真相源。
  ③ 明文/弱边界          → settings.json 0600（POSIX）、占位符不可用。

修复前：本文件大量 RED（证明 bug）。Gemini 按阶段 E 修完后应全部 GREEN。
跑法：python -m pytest backend/tests/test_tmdb_key_flow.py -v

目标后端契约（修复后应满足）
-----------------------------------------------------------------
1) get_effective_tmdb_key() -> str：优先 settings.json，其次 env TMDB_API_KEY，
   否则 ""；"${TMDB_API_KEY}" 占位符与含 '*' 的掩码值一律视为"未配置"。
2) GET  /api/settings -> {"has_key": bool, "key_hint": "****<last4>" | ""}
   且响应中**不含** "tmdb_api_key" 字段（杜绝回灌）。
3) POST /api/settings：
   - 空 / 纯空白 key   → 保持原值，不覆盖（200）。
   - 含 '*' 的掩码值   → 拒绝（400），不覆盖。
   - "${TMDB_API_KEY}" → 视为未配置（不写入真值）。
   - 合法新 key        → 写入，并能被 resolver 读到。
4) settings.json 落盘权限 0600（仅 POSIX）。
"""

from __future__ import annotations

import json
import os
import stat

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.main import app

REAL_KEY = "abcdef1234567890deadbeefcafebabe"  # 32 chars, 合法形态


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """把 SETTINGS_FILE 指向临时文件，隔离真实 ~/.config，并清空相关 env。"""
    p = tmp_path / "settings.json"
    monkeypatch.setattr(main, "SETTINGS_FILE", p, raising=True)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    return p


@pytest.fixture
def client(settings_file):
    return TestClient(app)


def _write_settings(path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tmdb_api_key": key}), encoding="utf-8")


def _read_key(path) -> str:
    if not path.exists():
        return ""
    return json.loads(path.read_text(encoding="utf-8")).get("tmdb_api_key", "")


def _resolver():
    """懒加载 resolver；未实现时给出明确的 RED 信息（阶段 E 任务 E1）。"""
    fn = getattr(main, "get_effective_tmdb_key", None)
    if fn is None:
        pytest.fail("backend.main.get_effective_tmdb_key 未实现（plan 阶段 E·E1）")
    return fn


# ===========================================================================
# E0 根因：/api/settings 路由被 app.mount("/", StaticFiles) 遮蔽 → 404
# （路由定义在 main.py 的 StaticFiles 挂载之后，被 catch-all 吃掉）
# ===========================================================================
class TestSettingsRoutesReachable:
    def test_e0_get_settings_not_shadowed_by_static_mount(self, client):
        r = client.get("/api/settings")
        assert r.status_code != 404, (
            "GET /api/settings 返回 404 —— 路由被 app.mount('/') 遮蔽。"
            "修复：把 StaticFiles 挂载移到所有 /api 路由之后（E0）。"
        )

    def test_e0_post_settings_not_shadowed_by_static_mount(self, client):
        r = client.post("/api/settings", json={"tmdb_api_key": REAL_KEY})
        # StaticFiles 挂载对 POST 返回 405、对 GET 返回 404，均表示没命中真正 handler
        assert r.status_code not in (404, 405), (
            "POST /api/settings 被静态挂载遮蔽（404/405）—— handler 未命中（E0）。"
        )


# ===========================================================================
# GET 契约：永不回吐可用 key
# ===========================================================================
class TestGetSettingsContract:
    def test_e_get_returns_has_key_field(self, client):
        r = client.get("/api/settings")
        assert r.status_code == 200
        assert "has_key" in r.json(), "GET 应返回 has_key 布尔字段"

    def test_e_get_omits_usable_key_field(self, client, settings_file):
        # 即使已配置真 key，响应里也不能出现 tmdb_api_key（防回灌自毁）
        _write_settings(settings_file, REAL_KEY)
        r = client.get("/api/settings")
        assert r.status_code == 200, "GET /api/settings 不应 404（路由被静态挂载遮蔽，见 E0）"
        assert "tmdb_api_key" not in r.json(), "GET 不得返回 tmdb_api_key 字段"

    def test_e_get_has_key_true_with_hint(self, client, settings_file):
        _write_settings(settings_file, REAL_KEY)
        body = client.get("/api/settings").json()
        assert body["has_key"] is True
        # key_hint 仅供展示，应只暴露尾 4 位
        assert body.get("key_hint", "").endswith(REAL_KEY[-4:])
        assert REAL_KEY not in body.get("key_hint", "")

    def test_e_get_has_key_false_when_empty(self, client, settings_file):
        # 无配置文件 → has_key False
        assert settings_file.exists() is False
        body = client.get("/api/settings").json()
        assert body["has_key"] is False


class TestValidateSettingsContract:
    def test_validate_false_when_missing_key(self, client):
        body = client.get("/api/settings/validate").json()
        assert body == {"has_key": False, "valid": False}

    def test_validate_reports_invalid_key(self, client, settings_file, monkeypatch):
        _write_settings(settings_file, REAL_KEY)

        async def fake_validate(self):
            return False

        monkeypatch.setattr(main.TmdbClient, "validate_key", fake_validate)
        body = client.get("/api/settings/validate").json()
        assert body == {"has_key": True, "valid": False}

    def test_validate_reports_valid_key(self, client, settings_file, monkeypatch):
        _write_settings(settings_file, REAL_KEY)

        async def fake_validate(self):
            return True

        monkeypatch.setattr(main.TmdbClient, "validate_key", fake_validate)
        body = client.get("/api/settings/validate").json()
        assert body == {"has_key": True, "valid": True}


# ===========================================================================
# POST 契约：防空覆盖 / 防掩码 / 防占位符
# ===========================================================================
class TestPostSettingsGuards:
    def test_e_empty_key_does_not_overwrite(self, client, settings_file):
        _write_settings(settings_file, REAL_KEY)
        r = client.post("/api/settings", json={"tmdb_api_key": ""})
        assert r.status_code in (200, 400)
        assert _read_key(settings_file) == REAL_KEY, "空值不得覆盖已有 key"

    def test_e_whitespace_key_does_not_overwrite(self, client, settings_file):
        _write_settings(settings_file, REAL_KEY)
        r = client.post("/api/settings", json={"tmdb_api_key": "    "})
        assert r.status_code in (200, 400), "POST /api/settings 不应 404（见 E0）"
        assert _read_key(settings_file) == REAL_KEY, "纯空白不得覆盖已有 key"

    def test_e_masked_value_rejected(self, client, settings_file):
        # 模拟前端把掩码值回灌
        _write_settings(settings_file, REAL_KEY)
        r = client.post("/api/settings", json={"tmdb_api_key": "abcde***"})
        assert r.status_code == 400, "含 '*' 的掩码值应被拒绝"
        assert _read_key(settings_file) == REAL_KEY, "掩码值不得覆盖真 key"

    def test_e_placeholder_treated_as_unconfigured(self, client, settings_file):
        client.post("/api/settings", json={"tmdb_api_key": "${TMDB_API_KEY}"})
        # 不论是否写入文件，has_key 必须为 False
        assert client.get("/api/settings").json()["has_key"] is False

    def test_e_valid_key_saved_and_effective(self, client, settings_file, monkeypatch):
        monkeypatch.setattr(main, "SETTINGS_FILE", settings_file, raising=True)
        r = client.post("/api/settings", json={"tmdb_api_key": REAL_KEY})
        assert r.status_code == 200
        assert client.get("/api/settings").json()["has_key"] is True
        # 单一真相源也应能读到（resolver 必须实现）
        assert _resolver()() == REAL_KEY


# ===========================================================================
# resolver 单一真相源：settings.json → env → ""
# ===========================================================================
class TestEffectiveKeyResolver:
    def test_e_resolver_reads_settings_file(self, settings_file):
        _write_settings(settings_file, REAL_KEY)
        assert _resolver()() == REAL_KEY

    def test_e_resolver_env_fallback(self, settings_file, monkeypatch):
        # 无 settings 文件，env 提供 key
        assert settings_file.exists() is False
        monkeypatch.setenv("TMDB_API_KEY", "env_key_1234567890")
        assert _resolver()() == "env_key_1234567890"

    def test_e_resolver_settings_precedence_over_env(self, settings_file, monkeypatch):
        _write_settings(settings_file, REAL_KEY)
        monkeypatch.setenv("TMDB_API_KEY", "env_key_should_lose")
        assert _resolver()() == REAL_KEY, "settings.json 应优先于 env"

    def test_e_resolver_ignores_placeholder_and_empty(self, settings_file, monkeypatch):
        _write_settings(settings_file, "${TMDB_API_KEY}")
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        assert _resolver()() == "", "占位符应被视为未配置"


# ===========================================================================
# 落盘安全：明文文件权限收敛（POSIX）
# ===========================================================================
class TestAtRestHardening:
    @pytest.mark.skipif(os.name == "nt", reason="Windows 无 POSIX 权限位")
    def test_e_settings_file_permissions_0600(self, client, settings_file):
        client.post("/api/settings", json={"tmdb_api_key": REAL_KEY})
        assert settings_file.exists()
        mode = stat.S_IMODE(os.stat(settings_file).st_mode)
        assert mode == 0o600, f"settings.json 权限应为 0600，实际 {oct(mode)}"
