# 02 · TMDB API Key 全链路修复（P1 · 安全+功能）

- **分类**: bugfix / 安全
- **优先级**: P1（症状：前端能输入 key 但"根本没用"）
- **前置依赖(Blocker)**: **E0 必须最先做**；E1–E4 依赖 E0（路由可达后才测得了）
- **验收测试**: `backend/tests/test_tmdb_key_flow.py`（目标契约见该文件顶部 docstring）
- **验收命令**: `python -m pytest backend/tests/test_tmdb_key_flow.py -q`

> 根因有 4 段，**E0 是第一性原因**，请严格按 E0→E1→E2→E3→E4 顺序做。

---

## E0（★根因）`/api/settings` 路由被静态挂载遮蔽 → GET 404 / POST 405
文件 `backend/main.py`。第 645 行 `app.mount("/", StaticFiles(directory="frontend", html=True))`
是 catch-all，而 `@app.get/post("/api/settings")`（667–685 行）**定义在它之后** → 被吃掉：
GET 404 / POST 405 → 前端 `api.js` 静默回退 mock → **key 从没进过后端**。

修复：把 **StaticFiles 挂载移到文件最末尾、所有 `/api` 路由注册之后**。
确保所有 `/api/*` 路由都在 mount 之前注册。
验证：`TestSettingsRoutesReachable` 两条转绿（GET≠404、POST∉{404,405}）。

---

## E1 引入单一真相源 `get_effective_tmdb_key()`（消灭 config 陈旧）
背景：`config = load_config()` 在 import 时冻结一次；`AppConfig` 用 `env_prefix="APP_"`，
根本不读裸 `TMDB_API_KEY`，所以 UI 存的 key 永远刷不进 `config`。

`backend/main.py` 新增：
```python
def get_effective_tmdb_key() -> str:
    """唯一真相源：settings.json > env TMDB_API_KEY > ""；占位符/掩码视为未配置。"""
    key = _load_settings().get("tmdb_api_key", "") or ""
    if key and "*" not in key and key != "${TMDB_API_KEY}":
        return key
    env = os.environ.get("TMDB_API_KEY", "") or ""
    if env and env != "${TMDB_API_KEY}":
        return env
    return ""
```
改造：所有用 key 处改调它——尤其 `watcher.tmdb_async_resolve`（watcher.py:15–26 手写兜底整段替换为一行调用）。
验证：`TestEffectiveKeyResolver` 4 条转绿。

---

## E2 `GET /api/settings` 永不回吐可用 key（防"掩码回灌自毁"）
`backend/main.py` `get_settings`（667 行）改为：
```python
    key = get_effective_tmdb_key()
    return {"has_key": bool(key), "key_hint": (f"****{key[-4:]}" if key else "")}
```
**不再返回 `tmdb_api_key` 字段。**

配套前端 `frontend/js/app.js`（`renderSettings`/`saveTmdbKey`，797/801 行）：
输入框**初始为空**，用 `has_key`/`key_hint` 显示"已配置 ****1234，留空则不变"；输入为空则不提交。
验证：`TestGetSettingsContract` 4 条转绿。

---

## E3 `POST /api/settings` 加守卫（防空覆盖 / 防掩码 / 防占位符）
`backend/main.py` `update_settings`（675 行）逻辑改为：
```python
    raw = (payload.get("tmdb_api_key") or "").strip()
    if not raw:
        return {"status": "unchanged"}            # 空/空白 → 不覆盖
    if "*" in raw:
        raise HTTPException(400, "masked value rejected")
    if raw == "${TMDB_API_KEY}":
        return {"status": "unchanged"}            # 占位符 → 不写真值
    settings["tmdb_api_key"] = raw
    _save_settings(settings)
    os.environ["TMDB_API_KEY"] = raw
    return {"status": "settings updated"}
```
验证：`TestPostSettingsGuards` 5 条转绿。

---

## E4 落盘安全：`settings.json` 权限收敛 0600（POSIX）
`backend/main.py` `_save_settings`（659 行）写完后：
```python
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass   # Windows 无 POSIX 权限位，忽略
```
另：README/SETUP 应说明可改用 `TMDB_API_KEY` 环境变量 / docker secret 作为首选来源。

---

## 📋 Linux 待办（Windows 侧不修，转交 Linux）
- [ ] 在 Linux 跑 `pytest backend/tests/test_tmdb_key_flow.py::TestAtRestHardening -v`，确认 `settings.json` 权限 == `0o600`。
- [ ] 在 Linux 跑完整 `pytest backend/tests -q`，确认 POSIX-only 路径全绿。
