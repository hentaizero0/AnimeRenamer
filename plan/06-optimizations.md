# 06 · 优化 / 小重构（P2 · 可选，逻辑等价提质）

- **分类**: optimization
- **优先级**: P2（可选；逻辑等价，提升质量与性能）
- **前置依赖(Blocker)**: 无硬依赖；但 D1/D2/D3 与 `05-refactor` 的 Phase 6/7/2 重叠，
  **若决定做整体重构，则这些并入重构 Phase，不要重复做**
- **验收**: 现有 `python -m pytest backend/tests -q` 持续 0 failed（行为等价）

> 这些都是结构性改动，Gemini 易写错。**给完整目标代码模板，别让它自由发挥**，并放在靠后批次。

---

## D1 — `main.py` `@app.on_event` 已废弃 → 改 lifespan
第 59、79 行 `@app.on_event("startup"/"shutdown")` 在新版 FastAPI 已 deprecated。
改用 `lifespan` async context manager 传给 `FastAPI(lifespan=...)`。
⚠️ Gemini 容易写错 startup/shutdown 搬迁顺序 → 给它**完整目标代码模板**。
（若做重构，此项并入 `05` Phase 6。）

---

## D2 — `tmdb.py` 复用 httpx 客户端
`search_anime`/`verify_episode` 每次都 `async with httpx.AsyncClient()` 新建连接。
改为在 `TmdbClient.__init__` 建长生命周期 client（或单例），减少握手开销。
⚠️ 涉及关闭时机，中等难度，需明确生命周期说明 → 靠后做。
（若做重构，此项并入 `05` Phase 7。）

---

## D3 — `triage.py` / `main.py` 抽公共逻辑
`execute_triage_job`(triage.py) 和 `preview_job`(main.py:265) 各自重复了 mode 解析、
`link_dir` 选择、`video_stems_by_ep` 预计算、目标文件名拼接 → 抽成纯函数
`compute_target_for_item(...)` 共用，保证预览与执行**永远一致**。
⚠️ 跨文件重构，对小 context 偏难。**放最后**，拆"先抽函数 → execute 用 → preview 用"三步交付。
（**与 `05` Phase 2 `naming.py` 是同一件事**——做重构就别单独做 D3。）

---

## D4 — 前端 `api.js` `_checkOnline()` 加 TTL
`_checkOnline()`（7 行）一旦 `_apiOnline===true` 就永久返回 true（8 行 early return），
后端中途挂了不会重测 → 加 TTL 或失败时重置。优先级最低。
