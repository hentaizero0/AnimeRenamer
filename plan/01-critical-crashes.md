# 01 · 致命崩溃修复（P0）

- **分类**: bugfix
- **优先级**: P0（不修，confirm 整理 / auto 整理 / 扫描无视频目录都会直接崩）
- **前置依赖(Blocker)**: 无，最先做
- **验收测试**: `backend/tests/test_plan_acceptance.py`
  - `TestA1ExecutedMovesRollback`、`TestA2NoEpisodeBranch`、`TestA3UuidImport`
- **验收命令**: `python -m pytest backend/tests/test_plan_acceptance.py -q`

---

## 批次 1（极易）

### A1 — `triage.py`：`executed_moves` 未定义
文件 `backend/triage.py`，函数 `execute_triage_job`（约 56–205 行）。
第 129/134/169 行用了 `executed_moves` 做回滚，但**从没定义**，第一次成功移动即 `NameError`。

修复：在函数体开头（`overall_success = True` 附近，约 80–81 行）加一行：
```python
    overall_success = True
    error_msg = None
    executed_moves: list[tuple[Path, Path]] = []   # 新增：记录已移动文件用于回滚
```
验证：第一次 `.append` 之前一定先有 `executed_moves: list... = []`。

### A3 — `watcher.py`：`uuid` 未 import
文件 `backend/watcher.py` 第 246 行 `id=str(uuid.uuid4().hex[:12]),`，顶部没 `import uuid`，
扫描"无视频目录"走 ignored 分支时 `NameError`。

修复（与同文件 254 行风格一致，改时间戳）：
```python
            id=str(int(time.time() * 1000)),
```
验证：搜不到 `uuid` 残留（或退而求其次在顶部 `import uuid`，二选一）。

> 批次 1 做完跑测试，`TestA1...test_a1_confirm_success...` 和 `TestA3...` 应转绿。

---

## 批次 2（需小心缩进）

### A2 — `triage.py`：无集数分支 `res` 未定义 + 缩进错乱
文件 `backend/triage.py` 约 151–177 行（`else:  # No episode detected` 分支）。
两个 bug：(1) auto 模式不走 `rename_and_move`，`res` 未定义却被下面读取 → NameError；
(2) 失败处理 `if not res.success` 被错误嵌进 `if res.success` 内部，永远进不去。

把这段改成：
```python
            if mode == "auto":
                # auto 模式：无集数文件原地保留，不移动
                continue
            target_file = storage_dir / anime_name / f"Season {season_str}" / rel_to_anime
            res = rename_and_move(source_file, target_file, dry_run)
            if res.success and not dry_run:
                executed_moves.append((source_file, target_file))
            if not res.success:
                overall_success = False
                error_msg = res.error_msg
                break
```
验证：`res` 被读前一定先 `res = rename_and_move(...)`；`if not res.success` 与 `if res.success` 平级。
参考断言：`TestA2NoEpisodeBranch`（confirm 落到 Season 目录、auto 原地保留）。

> 批次 2 做完跑全量 `python -m pytest backend/tests -q`，确认 A 段全绿且无新红。
