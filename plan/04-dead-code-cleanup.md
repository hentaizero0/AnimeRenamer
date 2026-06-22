# 04 · 死代码 / 冗余清理（P2）

- **分类**: cleanup（纯删除，零风险，最适合 Gemini）
- **优先级**: P2
- **前置依赖(Blocker)**: 无
- **验收测试**: `backend/tests/test_plan_acceptance.py`
  - `TestC1MainDeadCode`、`TestC2ParserDeadCode`、`TestC3DuplicateFiles`
- **验收命令**: `python -m pytest backend/tests/test_plan_acceptance.py -q`

> 守则：每删一个符号，先 grep 该名字确认除定义处外无引用，再删。

---

## C1 — `main.py` 删两段死代码
文件 `backend/main.py`。
- (a) 第 510–511 行：`return [...]` 之后还有一行 `return series_db._series`，**永远执行不到** → 删第 511 行。
- (b) 第 571–572 行：`if False:  # ...` 整块是死代码（路径校验已由上面 `relative_to` 做） → 删这两行。

验证：`TestC1MainDeadCode` 转绿（`return series_db._series` 与 `if False:` 都消失）。

---

## C2 — `parser.py` 删未使用符号
文件 `backend/parser.py`。
- (a) `_ParseState` dataclass（约 162–173 行）：全文件只定义、从不使用 → 删整个 class。
- (b) 删后顶部 `from dataclasses import dataclass, field`（26 行）若不再被用到 → 删/改该 import（先 grep `dataclass`/`field` 确认）。
- (c) `_TRAILING_TITLE_DIGIT_RE`（约 134–136 行）：定义了但 `_parse_stem`（538 行）用的是内联正则，没用它 → 删该常量。

验证：`TestC2ParserDeadCode` 转绿（两符号消失 + parser 解析功能回归不变）。

---

## C3 — 仓库根目录重复 / 临时文件（**分步删，每步单独确认**）
- (a) `reset_env.py`（根）与 `scripts/reset_env.py` **内容完全相同（均 3467 字节）** →
  删根目录那个，保留 `scripts/reset_env.py`，同步更新 README 引用路径。
  验证：`TestC3DuplicateFiles` 转绿。
- (b) `scripts/test_*.py` + `scripts/test_toggle.js`：开发期一次性手搓脚本（正式测试在 `backend/tests/`）。
  确认无 CI 引用后整批删。
- (c) 根目录 `result.md`、`unriad.output`、`.coverage`：开发产物。`.coverage` 进 `.gitignore`；
  `result.md`/`unriad.output` 评估后删或移到 `scripts/`。

> (a)(b)(c) 一次只做一类，分别确认。

---

## C4 — 旧 shell 脚本（⚠️ 用户决策，Gemini 不自作主张）
`anime_renamer.sh`(20KB)、`hardlink_creator.sh`(9.5KB)、`change_own.sh`：v1 时代脚本，已被 Python 后端取代
（README 第 293 行明说 `change_own.sh` "可以退休"）。**由用户确认是否还在 Unraid 上跑**，确认废弃后再删。
