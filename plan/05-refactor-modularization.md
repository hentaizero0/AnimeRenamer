# 05 · 整体重构 · 模块化（P2）

- **分类**: refactor
- **优先级**: P2（让未来加功能 + 让 AI 改代码都更容易）
- **前置依赖(Blocker)**: **必须 01–04 全部修完且 `pytest backend/tests -q` 0 failed** 才能开始
- **策略**: 绞杀者模式（strangler），旧代码始终能跑，一次搬一个模块
- **铁律**: 每个 Phase 后跑全量测试必须 0 failed，否则回退
- **验收**: 现有测试零修改持续通过（行为等价）；新增模块各配 `test_<module>.py`

> 这是硬骨头。**每个 Phase 单独喂 Gemini**，Phase 5/6 还要再拆 2–3 小步并给完整代码骨架。

---

## 为什么重构（现状 4 大病灶）
1. **隐式全局 + 循环耦合**：`queue`/`history` 是 `main.py` 全局，`watcher.py` 用
   `import backend.main as main_api` 反向读写 → 小 context 模型 hold 不住。（最优先消灭）
2. **HTTP 层塞满业务逻辑**：`main.py` 687 行，端点混着预览/merge/stats/清理，无法脱离 FastAPI 单测。
3. **同一逻辑多份拷贝且打架**：preview/execute 两份路径拼接会漂移；
   **视频后缀名散落 4+ 处不一致**（parser 9 种 vs watcher 漏 rmvb vs 字幕 .ssa 时有时无）；mode 解析重复。
4. **无边界**：IO（fs/httpx/yaml）和纯逻辑混在一起；到处 `print()`；路径硬编码。

## 目标架构（分层，依赖只能从上往下）
```
backend/
  domain/      # 纯逻辑，无 IO 无框架
    constants.py  # ★唯一真相源 VIDEO_EXTS/SUB_EXTS/EXTRAS_KEYWORDS
    models.py  parser.py
    naming.py     # ★算目标文件名/路径——消灭 preview/execute 拷贝
    mode.py       # ★auto/confirm 解析集中
  services/    # 编排
    triage_service.py  scanner.py  tmdb_service.py
    queue_service.py   # ★queue/history 唯一持有者，消灭全局
  adapters/    # IO 边界
    fs.py  tmdb_client.py  config_store.py  state_store.py  watcher.py
  api/         # 薄 FastAPI
    app.py  deps.py  routes/{queue,history,series,directories,settings}.py
```
依赖方向：`api → services → domain`，`services → adapters`，`domain` 不依赖任何人。

## 分阶段（从叶子往根搬，风险递增）

| Phase | 模块 | 风险 | 价值 | 说明 |
|---|---|---|---|---|
| 1 | `domain/constants.py` | ★ | 高 | 集中后缀/extras，**顺修 rmvb/ssa 不一致 bug**；逐文件替换引用 |
| 2 | `domain/naming.py` | ★★ | 高 | 抽 `compute_target(...)` 纯函数，preview 与 execute 都调它（防漂移） |
| 3 | `domain/mode.py` | ★★ | 中 | `resolve_mode(job, config)`，含冲突降级；三处改调它 |
| 4 | `adapters/fs.py` | ★★ | 中 | 搬 rename/hardlink/rollback，签名不变；现有 test_triage 不改应通过 |
| 5 | `services/queue_service.py` | ★★★★ | **最高** | 持有 queue/history，watcher 改为**注入**，干掉 `import backend.main`。拆 3 小步：(a)建类+测试 (b)main 改用 (c)watcher 注入 |
| 6 | `api/` 拆分 | ★★★★ | 高 | `create_app()` 工厂 + lifespan（含 D1）+ 路由分文件；保留 `backend/main.py` 薄壳 `app=create_app()` 兼容旧测试 import |
| 7 | 收尾 | ★★ | 中 | `adapters/state_store.py`；`print()`→`logging`；tmdb 复用连接(D2)；删 `__pycache__`；更新 README 架构 |

> 顺序铁律：1→2→3→4→5→6→7，每步全量测试 0 failed 才前进。

## 给 AI 友好的长期约定（写进未来 CONTRIBUTING/AGENTS）
- domain 层**禁止** import fastapi/httpx/写文件 → 保证可纯单测。
- 每模块顶部一句话职责注释；公共函数全类型标注 + 短 docstring。
- 一次 AI 交付只动一层；新功能先在 domain 加纯函数+测试，再往上接。
