# 03 · 逻辑 Bug 修复（P1）

- **分类**: bugfix
- **优先级**: P1（结果不对，但不一定崩）
- **前置依赖(Blocker)**: **B1 BLOCKED —— 需用户先拍板语义**；B2/B3 无依赖
- **验收测试**: `backend/tests/test_plan_acceptance.py`
  - `TestB1OverrideEpisode`、`TestB2SeriesPersistence`、`TestB3SearchSignature`
- **验收命令**: `python -m pytest backend/tests/test_plan_acceptance.py -q`

---

## B2 — `config.py`：`SeriesDB.save()` 用 `exclude_unset=True` 丢字段
文件 `backend/config.py` 第 59 行。`exclude_unset=True` 只导出"显式设过的字段"，
程序构造的 SeriesConfig（如 TMDB 解析出来的）存盘会**丢掉 mode/season 等默认值**。

修复：
```python
            series_dict[title] = s_conf.model_dump(exclude_none=True)
```
验证：`TestB2SeriesPersistence` 转绿（mode/season 被写进 yaml 且 reload 稳定）。

---

## B3 — `tmdb.py`：`search_anime` 收了 `season` 参数却从不使用
文件 `backend/tmdb.py` 第 30 行。`season` 参数函数体完全没用，误导。

修复：删参数 → `async def search_anime(self, title: str) -> list[TmdbMatch]:`
**改前先 grep** 确认无调用方传 season（`watcher.py:36/49` 都没传，安全）。
验证：`TestB3SearchSignature` 转绿（签名无 season + 空 key 返回空）。

---

## B1 — `override_episode` 存了却从不生效  ⚠️ BLOCKED
现状：`BatchTriageJob.override_episode`（models.py:137）能经 `PATCH /api/pending/{id}`（main.py:427）写入，
但 `execute_triage_job` 和 `preview_job` 重命名时**完全没用它**。

### ⛔ Blocker：先让用户二选一语义，再让 Gemini 写
- **语义 A**：override_episode = 整个 job 第一个文件的"起始集号"，按顺序依次 +1。
- **语义 B**：override_episode = 强制把（唯一）视频设为该集号。

当前验收测试 `TestB1OverrideEpisode` 按"单视频强制该集号"写（A/B 都满足）。
确认语义后，在 `triage.py` 计算 episode 处（约 104 行
`episode = it.parsed.episode if it.parsed else None`）插入 override 逻辑，
`preview_job` 同步。验证：`TestB1OverrideEpisode` 转绿。

> 在用户回复语义之前，**B1 保持搁置**，先做 B2、B3。
