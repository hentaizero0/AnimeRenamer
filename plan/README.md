# AnimeRenamer 改造计划（索引）

> 本目录把工作拆成按分类的小文件，**一次只喂 Gemini 一个文件**。
> 每个文件都自带：目标、前置依赖(Blocker)、验收测试、可照抄的修复代码、验证命令。

## 文件一览 / 执行顺序

| 顺序 | 文件 | 分类 | 优先级 | 前置依赖(Blocker) |
|---|---|---|---|---|
| 1 | [01-critical-crashes.md](01-critical-crashes.md) | bugfix | P0 | 无 |
| 2 | [02-tmdb-api-key.md](02-tmdb-api-key.md) | bugfix/安全 | P1 | E1–E4 依赖 E0 先做 |
| 3 | [03-logic-bugs.md](03-logic-bugs.md) | bugfix | P1 | B1 需用户先定语义 |
| 4 | [04-dead-code-cleanup.md](04-dead-code-cleanup.md) | cleanup | P2 | 无 |
| 5 | [05-refactor-modularization.md](05-refactor-modularization.md) | refactor | P2 | **必须 1–4 全绿后**才能开始 |
| 6 | [06-optimizations.md](06-optimizations.md) | optimization | P2 | D2/D3 建议并入重构 |

## 依赖关系图

```
01-critical-crashes ─┐
02-tmdb-api-key ─────┤
03-logic-bugs ───────┼──► (全绿基线) ──► 05-refactor ──► 06-optimizations(D2/D3)
04-dead-code ────────┘
   E0 ──► E1,E2,E3,E4         B1 ──BLOCKED── 等用户拍板 override_episode 语义
```

## 验收测试（spec / 真相源）

两份测试就是验收标准，现在是红的（故意，证明 bug 存在），修完应转绿：
- `backend/tests/test_plan_acceptance.py` — 对应 01/03/04
- `backend/tests/test_tmdb_key_flow.py` — 对应 02

基线：32 个测试，当前 **30 RED + 1 skipped(Windows 权限)+ 1 passed(回归)**。

验收命令：
```bash
python -m pytest backend/tests -q                       # 全量，目标 0 failed
python -m pytest backend/tests/test_plan_acceptance.py -v
python -m pytest backend/tests/test_tmdb_key_flow.py -v
```

## 给 Gemini 的统一作业守则（每个任务先贴这段）

```
你在修改 Python 3.14 + FastAPI 项目 AnimeRenamer。规则：
1. 一次只做当前文件里的一个批次，做完就停，输出 diff，等我确认。
2. 改前先 view 出点名的真实代码，确认和描述一致再改；只改点名文件，别动无关代码。
3. 每批做完跑 python -m pytest backend/tests -q，必须 0 failed（Windows 上权限测试 skip 属正常）。
4. 注释要短；不要重构无关代码；不要改格式风格。
5. 不懂某条要做什么，就去读对应的验收测试断言——它就是标准。
```

## 环境

- 开发机：Windows + Python 3.14.6，依赖已 `pip install -r requirements.txt`。
- 部署：Linux/Unraid。**POSIX 专属项（0600 权限、hardlink）在 Windows 上 skip，由 Linux 侧验证**（见 02 文件末尾 Linux 待办）。
