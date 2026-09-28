# 08 — 动画名称与季度识别错误修复计划

> 类型：bugfix / 识别与季集判定；优先级：P1。本文仅制定修复计划，没有实施业务代码修复。审计日期：2026-09-28 UTC。
> **环境约定：用户已确认使用本地 regression 环境作为 production 问题复现环境。以下“已确认”指当前代码对既有文件名清单的隔离回放；不是生产现场或运行中队列的逐项观测。**

## 1. 目标与范围

修正文件名清洗、作品消歧、季集选择和最终命名之间的信息丢失，保留正确对照，避免把系列规范标题、季标题、发行季度、TMDB 季号及绝对集数混为一谈。完成本计划不意味着修复已经上线。

本次只读取仓库、既有文本 fixture、允许的只读 API；运行纯解析测试和隔离内存回放。没有调用扫描、确认、重新处理、修改队列接口，没有启动 watcher，没有读取媒体内容或枚举媒体目录，没有移动、重命名、删除媒体或创建硬链接，也没有修改权限。

### 环境与基线

- 仓库：`/workspaces/anime_triage`；HEAD：`1f69441a8f0e7ce1665d7da9b8ab14328a4529b4`。结论针对**当前工作区内容**，不能仅凭 HEAD 重建本次结果：`backend/parser.py`、`backend/tmdb.py`、`backend/watcher.py` 等已有未提交改动；`backend/tests/test_tmdb_steel_ball_run.py` 为已有未跟踪测试。本次没有覆盖这些改动。
- `plan/` 实有 01–06；`plan/README.md` 已登记 07 日志计划，虽然对应文件当前不存在，仍保留其编号。因此使用 **08**，索引只追加。
- 本地运行服务：`http://127.0.0.1:8765`；进程工作目录为本仓库。当前 `config/series_config.yaml` 的下载路径为 `/workspaces/anime_triage/regression_downloads/Downloads`，存储路径为 `/workspaces/anime_triage/regression_target/mnt/user/hentaidisk/video/anime`。这是 **regression 环境**；用户随后明确指定用它作为 production 问题的复现环境。本文按这一约定交付，不再等待另一个 test 地址；仍不把它说成生产现场。
- 2026-09-28 UTC 审计期间，安全读取 `/api/stats` 得到 pending=14、processed_today=6、errors=0；`/api/series` 返回 `[]`，本地 YAML 的 `series` 也为空。统计只表示队列数量，不证明任何一个文件的识别正确或错误。
- 用户已确认环境选择；没有访问 production 现场。运行中 pending/preview 的原始 parsed、TMDB ID、override 来源及目标路径没有取得，这一限制不妨碍隔离回放和制定修复方案。
- 特别注意：当前 `GET /api/pending` 的 `backend/main.py:get_queue` 会执行 `src.rglob('*')` 统计文件大小；按本次“不要扫描媒体”要求未调用。前端首页会间接调用该接口和目录接口，因此也没有通过打开首页绕过限制。`GET /api/pending/{job_id}/preview` 只规划名称并检查已知文件是否存在，但本次没有安全取得当前 job ID，未调用。
- `unriad.output` 是仓库中的**既有目录树文本**，来源为历史 Unraid 导出，README 说明它用于生成 regression 数据。读取它不等于访问生产媒体，也不证明对应文件今天仍存在。旧 Playwright YAML 仅作为历史线索，不作为当前队列事实。

### 实际检查数量

| 层级 | 本次数量 | 能证明什么 |
|---|---:|---|
| 独立 test / production 现场文件识别/预览 | **0** | 用户选择本地复现，不把结果外推为现场观测 |
| 本地在线 regression 文件识别/预览 | **0** | 只读取 stats/series；14 个 pending 未逐项检查 |
| 既有 `unriad.output` 视频文件名纯解析 | **305** | 当前解析器对这 305 个文本输入的结果；不等于 305 部动画或 305 个已定性问题 |
| 重点清单解析→匹配→季集→目标路径隔离回放 | **126** | 冰海 48、Spy 13、赛马娘 28、魔女 12、Re:Zero 主篇 25 |
| JoJo 原始名称补充回放 | **2** | 第 1 集来自用户原始示例；第 2 集为同模板构造用例，不计作已发现的当前文件 |
| 重点回放合计 | **128** | 54 个问题输入，74 个正确对照（均受表内语义范围限制） |
| 其余清单输入 | **179** | 仅纯解析初筛，未完成作品匹配/编号语义核验，不能称为已全面排查 |
| 既有纯测试 | **76 passed** | `test_parser.py` + `test_tmdb_steel_ball_run.py`，未运行可能触发启动/媒体操作的全量套件 |

128 个输入为 126 个清单条目加 2 个示例，不是新增媒体。魔女另有 1 个 ANi 风格合成字符串仅作标签清洗探针，不纳入 128 的逐项回放统计。

## 2. 测试环境审计结果

### 2.1 重点结论表

下表“当前结果”统一指**当前工作区代码 + 本次实时 TMDB 查询结果 + 空的隔离队列**产生的回放，不是在线 test 的观测值。回放采用 confirm 模式、无人工 override，路径规划根为虚拟 `/audit/output`；仅拼接字符串，不创建该目录。输入完整相对路径及每集结果见附录 A；这些相对路径来自文本清单，真实当前绝对路径未知。

| 编号、状态/可信度 | 输入文件名/范围 | 当前识别作品、季、集 | 正确/期望作品、季、集 | 证据 |
|---|---|---|---|---|
| J1 正确对照，高（新解析链）；在线待核验 | `[Sakurato] Steel Ball Run：JoJo no Kimyou na Bouken [01][HEVC-10bit 1080p AAC][CHS&CHT].mkv`；另构造 `[02]` | `JOJO的奇妙冒险`，S06E01 / S06E02；TMDB 45790，score=1.0，matched_season=6 | 系列字段 `JOJO的奇妙冒险`（zh-CN）；季字段 `飆馬野郎`（zh-HK），第 6 季，E01/E02 | 当前 `parser.py`、`tmdb.py`、`watcher.py` 回放；[TMDB S6](https://www.themoviedb.org/tv/45790/season/6?language=zh-HK) 及实时 API |
| J2 疑似，需人工确认；旧清单存在，在线未知 | `Bangumi/飙马野郎 JOJO的奇妙冒险/Season 1/JOJO的奇妙冒险OVA S01E01.mkv`、`...S01E02.mkv` | 文本本身已是 OVA/S01；纯解析保持原值；单独搜索该标题返回 60862、score=1.0、matched_season=1 | 若确为 Steel Ball Run，目标应 45790/S06E01、E02；需原文件名/历史证据确认文件身份 | `unriad.output:96–99`，不能当成今天的文件或旧错误仍存在的证明 |
| V2 已确认（隔离回放），高 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E01-[1080p][BDRIP][x265.FLAC].mkv` 至 E24 | parser=`Vinland Saga`/S02/E01–24；最终=`冰海战记`/**S01**/E01–24 | `冰海战记`，**S02**，E01–24，TMDB 88803 | `unriad.output:123–146`；resolver 默认值及模型优先级；[TMDB S2](https://www.themoviedb.org/tv/88803/season/2) |
| V1 正确对照，高（该批发行季身份仍以来源为准） | `[BeanSub&LoliHouse] Vinland Saga - 01 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` 至 24 | parser 季=None，最终 `冰海战记`/S01/E01–24 | 按用户所指第一季，此结果正确：88803/S01/E01–24 | `unriad.output:148–171`；[TMDB S1](https://www.themoviedb.org/tv/88803/season/1) 有 24 集；文件名没有显式季号，不能用该回放证明所有同名发行都是 S1 |
| S3 已确认（隔离回放），高 | `[Sakurato] Spy x Family S3 [01][HEVC-10bit 1080p AAC][CHS&CHT].mkv` 至 13 | parser S03；最终 `间谍过家家`/**S01**/E01–13 | `间谍过家家`/**S03**/E01–13，120089 | `unriad.output:441–453`；[TMDB S3](https://www.themoviedb.org/tv/120089/season/3) 有 13 集 |
| U1 已确认标题污染，高；映射有实时元数据支持 | `Uma Musume Shinderera Gurei 2025 S01E17-[1080p][BDRIP][x265.OPUS].mkv`；18、19、22、23 同模板 | `Uma Musume Shinderera Gurei 2025 - .`/S01/E17、18、19、22、23；脏查询和目录 fallback 均无候选 | 清洗查询 `Uma Musume Shinderera Gurei`；系列 `赛马娘 芦毛灰姑娘`/S01/原集号，262700 | `unriad.output:101–106`；干净罗马字查询 score=1.0；[TMDB 262700](https://www.themoviedb.org/tv/262700) |
| U2 正确对照，高 | `[LoliHouse] Uma Musume Cinderella Gray - 01 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` 至 23 | `赛马娘 芦毛灰姑娘`/S01/E01–23 | 同当前，262700 | `unriad.output:416–438`；英文变体搜索 score=1.0，不能把该批也算标题错误 |
| B1 已确认标题污染，高 | `穹廬下的魔女 [Baha] S01E01.mp4` 至 E12，部分位于 `Season 1/` | `穹廬下的魔女 [Baha]`/S01/E01–12；原查询空，目录简体查询候选 288971 仅 0.2，被拒绝 | `穹庐下的魔女`（或选定语言的繁体规范标题），S01/E01–12；平台标签不进入作品名 | `unriad.output:82–95`；清洗规则；[TMDB 288971](https://www.themoviedb.org/tv/288971)；还有 B2 评分缺陷 |
| R1 正确对照（当前 TMDB 默认顺序），高；其他编号约定需人工确认 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26]...[CHS].mp4` 至 `[50END]` | `Re：从零开始的异世界生活`/S01/E26–50 | **按当前 TMDB 65942 默认顺序保持 S01E26–50**；只有明确采用发行季度/其他 episode group 时才讨论 S02E01–25 | `unriad.output:481–505`；[TMDB S1](https://www.themoviedb.org/tv/65942/season/1)，实时 API 验证 E26、E50；不能机械减 25 |

### 2.2 实时 TMDB 核验摘录

查询使用已有本地凭据，仅发送 GET；正文、日志和文档不记录密钥、认证头或含密钥 URL。网页工具直接访问用户链接失败，但同一 TMDB 官方 API 成功，因此 JoJo 结论来自实际 API 响应，不是凭链接猜测。核验时刻为本次审计时段；元数据以后可能变化。

| 查询/资源（省略认证参数） | 当前返回要点 |
|---|---|
| `search_anime('Steel Ball Run：JoJo no Kimyou na Bouken')` | 45790，`JOJO的奇妙冒险`，score 1.0，matched_season 6 |
| `search_anime('Steel Ball Run')` | 45790/1.0/S6；另有 336466/约 0.5698/无季匹配，证明不能只依赖第一个搜索结果或标题包含关系 |
| `GET /3/tv/45790?language=zh-CN` | 系列名称 `JOJO的奇妙冒险`，6 季 |
| 同资源 `language=zh-HK` | 系列名称 `JoJo 奇妙冒險`，不是 `飆馬野郎` |
| `GET /3/tv/45790/season/6?language=zh-HK` | season ID 451151，name=`飆馬野郎`，season_number=6，air_date=2026-03-19 |
| 同季 zh-CN / en-US | `飙马野郎篇` / `STEEL BALL RUN`；第 1、2 集均在季条目中。`(2026)` 是日期展示语义，不是 API 的系列 name 字段 |
| `search_anime('Vinland Saga')` | 88803/`冰海战记`/1.0/matched_season=None；另有 336053/0.7，需保留消歧负例 |
| `GET /3/tv/88803?language=zh-CN` | S1 24 集，S2 24 集；“集存在”不能单独区分这两季 |
| `search_anime('Spy x Family')` | 120089/1.0/matched_season=None；详情有 S1=25、S2=12、S3=13 集 |
| `search_anime('Uma Musume Shinderera Gurei 2025 - .')` | 空；清洗为 `Uma Musume Shinderera Gurei` 则命中 262700/1.0；英文 Cinderella Gray 也命中相同 ID |
| `search_anime('穹廬下的魔女 [Baha]')` | 空；`穹庐下的魔女` 和 `穹廬下的魔女` 都返回 288971，但当前计算分数仅 0.2 |
| `GET /3/tv/288971?language=zh-CN&append_to_response=alternative_titles` | 本地化 name 精确为 `穹庐下的魔女`，别名列表没有中文标题；当前评分没有使用这个本地化 name |
| `GET /3/tv/65942?language=zh-CN` | number_of_seasons=1，S1 episode_count=85；不要把发行季数硬套到该元数据结构 |
| `GET /3/tv/65942/season/1/episode/26`、`.../50` | E26=`各自的誓言`（2020-07-08）；E50=`月下乱舞`（2021-03-24） |

## 3. 实际代码路径与原因

### 3.1 全链路及优先级

```text
文件事件 / 显式扫描（本次均未触发）
  → watcher.process_directory
  → parser.parse_file(f.name) → _parse_stem
  → FileTriageItem(parsed) → BatchTriageJob
  → SeriesDB.match_entry_by_alias（精确匹配，本地配置）
  → 无 series_config 时 watcher.tmdb_async_resolve
  → TmdbClient.search_anime → _search_once → 候选及 matched_season
  → 写 job.series_config，并写 job.override_title
  → BatchTriageJob.effective_title / effective_season
  → main.preview_job → naming.compute_target_plan
  → triage._execute_triage_job_sync 复用同一 planner（仅阅读，未调用）
```

- 标题优先级：`override_title` → `series_config.tmdb_name` → 第一个有标题的 parsed → 目录名。注意解析器使用 basename；`process_directory` 不把父目录传入 `torrent_name`。
- 季号优先级：`override_season` → `series_config.season` → 第一个有季号的 parsed → `1`。一个 Batch 只有一个 effective season，所有 item 共用。
- 集号：`naming.effective_episode` 仅在一个 active item 时使用 `override_episode`，否则采用每个 parsed episode；没有通用“绝对集数转季度集数”的转换。视频加字幕也可能导致 active item 超过 1，已有计划 03 涉及该语义，不另行偷偷改变。
- `main.get_queue` 的 `original_parsed_title` 用多数票，但模型 effective title 用第一个 item；两者不是同一个计算来源。
- `frontend/js/app.js:renderPreview` 显示 API 的名称与路径，没有独立 TMDB 季推断。当前 V2/S3 是上游 effective season 错误，不能只改 UI。
- `TmdbClient._shared_clients` 缓存 HTTP 客户端，不是搜索结果缓存；`state_store` 仅持久化 history，不持久化 pending 队列。没有证据表明此次问题源自磁盘 TMDB 缓存。

### 3.2 V2 / S3：正确解析季号被默认季覆盖

定位：`backend/parser.py:_parse_stem`；`backend/watcher.py:63–70`；`backend/models.py:effective_season`；`backend/domain/naming.py:compute_target_plan`。

1. Vinland `S02E01` 先命中 `_SXEXX_RE`，得到 season=2、episode=1；Spy `S3 [01]` 得到 season=3、episode=1。126 个重点清单回放中相关每个文件均已核验，不是只抽查第一集。
2. 标题清洗后查 TMDB：88803 / 120089 均高分，但标题本身不是季标题，`matched_season=None` 是合理结果。
3. resolver 仍创建 `SeriesConfig(season=best_match.matched_season or 1)`，因此写入了**推测的默认 1**。
4. 模型把该配置置于 parsed season 之前，planner 统一生成 `Season 01/... S01E..`。这也使两个 Vinland 批次指向重叠目标路径；这里只证实路径规划冲突，没有执行文件覆盖。
5. `verify_episode` 没有被 resolver 调用；即使补调，由于 Vinland 两季都有 1–24 集，仅检查 E01 存在也不能确定是哪季。

**建议修复：**在 TMDB 结果转为有效季的共同入口保留季号来源。至少区分人工指定、本地配置、文件显式季、TMDB 已证实季、默认值；默认 1 不能高于显式 parsed。不要单纯把 `effective_season` 中所有配置统一降级，否则可能破坏用户刻意配置的编号映射。没有显式季时允许 JoJo 的已证实 S6；有明确冲突时进入人工确认，不把模糊季标题评分当作确定映射。

### 3.3 J1 / J2：JoJo 新输入当前正确，旧 OVA 因果尚未证实

当前查询全文可以返回 45790，`tmdb.py` 使用英文章标题 `STEEL BALL RUN` 的 partial/token 分数推断 S6。因此旧“必然识别为 OVA”不能复述成当前事实。已有 JoJo 测试也通过。

旧清单的文件名已经变成 `JOJO的奇妙冒险OVA S01E01/02`，以该字符串再查询会高分命中 60862；这是一条**错误名称可能自我延续**的路径，并不证明旧错误最初怎么发生。要补取当时原始 parsed title、候选列表、目录 fallback、选中 ID、是否存在 series config/override 才能判定最初是候选缺失、误排序还是旧状态残留。

`TmdbMatch` 只有系列 `name` 和 `matched_season`，没有 season title；现在 planner 使用系列名称是合理行为。若产品要显示季标题，应增加明确的季标题展示信息，与规范存储标题分开；不能把 `飆馬野郎 (2026)`直接写进当前系列 name 字段作为所谓修复。

### 3.4 U1：罗马字变体 + 标签残留 + 错误目录 fallback

定位：`parser.py:_JUNK_TAGS/_strip_junk_tags/_clean_title`；`watcher.py:33–48`；`tmdb.py:_search_once`。

- `S01E17` 提取正确；`[x265.OPUS]` 未被完整技术块规则移除，分步清理后遗留句点，`2025` 也未作为年份剥离，最终是 `Uma Musume Shinderera Gurei 2025 - .`。
- `_clean_title` 只清除空白/&/短横线组成的空括号，并未覆盖该标点残留。
- 查询污染后的标题没有候选。目录 `[BDrip] Uma Musume Shinderera Gurei S01 [7³ACG]` 被 resolver 简单取“第二个方括号内容”，实际得到字幕组 `7³ACG`，不是作品名，仍无结果。
- 干净罗马字 `Uma Musume Shinderera Gurei` 当前已能命中与 `Uma Musume Cinderella Gray` 相同的 262700，**没有证据要求新增罗马字转译服务或大规模手写别名字典**。

**建议修复：**复用现有解析器中的技术标签清洗，限定清理“纯技术括号块”和明确年份位置，不删除所有括号/数字；目录 fallback 解析可用标题并保留季号，不能按括号序号猜标题。保留正式标题内的年份、数字、括号负例。修复顺序先清洗再评估是否还需要别名。

### 3.5 B1 / B2：平台标签残留，且中文规范名未参与评分

定位：`parser.py:_extract_fansub/_JUNK_TAGS`；`tmdb.py:118–144`；`watcher.py:59`。

- `_extract_fansub` 只处理开头发布组；`[Baha]` 不是现有 junk tag，位于标题中后部会保留。当前清单 12 个输入均产生带标签标题。
- 即使通过目录得到干净简体标题，TMDB 已返回正确 ID 288971 和本地化 name，但评分仅比搜索返回名称、original_name、alternative_titles；没有比较用于最终显示的 `details['name']`。
- 本次候选中文不在 alternative_titles，得到 0.2，低于 resolver 的 `>0.6` 阈值，导致规范名没有写回。**只去掉 Baha 未必足以修复整条链路。**

**建议修复：**有限识别平台/发布标记，保留原始文件名；把请求语言的规范 name 纳入标题相似度证据，保留年份、原语言、国家、动画类型等消歧约束。避免为了这个样本降低全局阈值，使无关作品也能入选。标签处理、中文匹配及最终有效标题各有回归断言。

### 3.6 R1：Re:Zero 必须先约定 episode order

解析 `[26]` 和 `[50END]` 得到 26、50，未错误取区间边界；目录的 `[26-50END]` 不是单集文件名。清单主篇 25 个条目与 `SP/` 中 Break Time 的 25 个条目是不同集合，本次主链回放只包括前者。

当前 TMDB 65942 的默认顺序确实包含 S01E26 和 S01E50；所以 S01E26–50 是正确对照，不修成 S02E01–25。若用户希望按发行季度存储，需要显式选择编号来源/episode group，并建立有证据的映射；不能用 `episode > 25` 一条规则猜测。主篇、SP、重剪版必须分开验证。

### 3.7 额外线索与状态保留问题

| 状态 | 输入/场景 | 当前代码证据与风险 | 期望/待办 |
|---|---|---|---|
| 疑似，需人工确认 | `unriad.output:70–81` 的 `Bangumi/碧蓝之海/Season 2/碧蓝之海 S01E01.mp4` 至 E12 | 12 个文本输入 parsed season=1，与路径 Season 2 冲突；parser 只看 basename | 先确认媒体确为第二季及目标编号方案，再决定是否 S02E01–12；禁止仅凭父目录自动覆盖 |
| 疑似，需人工确认 | `unriad.output:66–67` 的 `Bangumi/相反的你和我/Season 2/正相反的你与我 S01E13.mp4`、E14 | parsed S1，文件夹 S2；同一动画下还有 Season 1 子目录 | 需要发行信息/编号约定；正确季集暂未知，不能计作已确认错误 |
| 已确认代码缺口；在线发生情况未知 | 人工设置 season/episode 后触发 `DownloadDirHandler.process_dir_event` | 刷新重建 job 时仅复制 `series_config`、`override_title`、`ignore_reason` 和 ignored 标记，**未复制 override_season / override_episode** | 保留用户季集选择；用内存替身验证事件刷新，禁止用真实媒体事件复现 |
| 已确认代码缺口；在线发生情况未知 | TMDB 异步任务完成前用户已修改标题 | resolver 无条件写 `override_title=best_match.name`，自动结果与人工修改共用字段，无来源或版本检查 | 标明来源，自动任务不能覆盖任务启动之后的人工改动；测试异步完成顺序 |
| 疑似，需验证实际任务 | 一个 Batch 内含多个 Season 文件夹或同集号不同季 | `process_directory` 收集多个 Season 子目录；模型只返回一个季；conflict 和 video stem 映射主要按 episode 键分组 | 决策：按作品+季拆 batch，或明确逐 item 季支持；至少阻止混季批次静默统一改季。回归 S01E01/S02E01，不将其当重复版本 |

没有在线队列原始字段时，不能把上述任何一个状态问题断定为旧 JoJo 或当前 test 的真实根因。

## 4. Debug 与安全复现步骤

### 4.1 先取得环境身份及安全快照

1. 本轮已按用户选择固定复现环境为 `http://127.0.0.1:8765`，路径见第 1 节；以后对比 production 时记录部署版本/工作区差异、download/storage 根目录及 fixture 身份，不混用现场和复现结论。
2. 使用现成的**不遍历媒体的内存队列导出**或用户提供的当前脱敏快照；当前项目没有这样的通用导出 API，这是在线核验的缺口。若未来增加，返回 job/items/parsed/配置来源即可，不能顺带触发 scan 或 watcher。
3. 对 snapshot 中每个 job 记录 `job_id`、`source_dir`、`relative_path`、`ignored`、`default_mode`、`parsed.detected_title/season/episode/confidence`、`series_config.tmdb_id/name/season`、`override_title/season/episode`、有效值及来源。接口不暴露来源时标未知，不猜“用户改过”。
4. 取得已知 job ID 后，先审阅**部署版本**的 preview 是否只读，再 GET preview；对照 `new_name/new_path/hardlink_path`。没有 job ID 不执行扫描来生成。
5. 无法取得在线快照时保留本计划的“在线 0 项”，而不是补写假设结果。JoJo 第二集是否仍在 test 必须重新确认。

### 4.2 本地最小可运行复现：显式季被覆盖

以下是测试/调试片段，不是生产修复；纯内存、无网络、无媒体访问。当前版本断言应通过，表明缺陷存在。修复后应将断言改为预期 S02。

```bash
cd /workspaces/anime_triage
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
import asyncio
from unittest.mock import patch
from backend.config import AppConfig
from backend.parser import parse_file
from backend.models import BatchTriageJob, FileTriageItem
from backend.services.queue_service import QueueService
from backend.tmdb import TmdbMatch
from backend.watcher import tmdb_async_resolve
from backend.domain.naming import compute_target_plan

async def main():
    name = 'Vinland Saga S02E01-[1080p][BDRIP][x265.FLAC].mkv'
    item = FileTriageItem(relative_path=name, is_video=True, parsed=parse_file(name))
    job = BatchTriageJob(id='audit', source_dir='.', items=[item])
    queue = QueueService()
    queue.put(job)
    cfg = AppConfig(_env_file=None, download_dir='/audit/input', storage_dir='/audit/output')
    async def search(self, title):
        return [TmdbMatch(88803, '冰海战记', 'ヴィンランド・サガ', 2, 1.0, None)]
    assert item.parsed.season == 2
    with patch('backend.tmdb.TmdbClient.search_anime', search):
        await tmdb_async_resolve('audit', 'Vinland Saga', '.', cfg, queue,
                                 key_resolver=lambda: 'fixture-key')
    assert job.effective_season == 1  # 当前缺陷，不是修复后期望
    # 明确给出视频 stem，模拟真实 preview 已知文件存在时的映射，不遍历文件。
    from pathlib import Path
    target = compute_target_plan(job, item, cfg, {1: [Path(name).stem]})
    assert str(target.target_file) == '/audit/output/冰海战记/Season 01/冰海战记 S01E01.mkv'
    print(item.parsed.season, job.series_config.season, job.effective_season,
          target.target_file)
asyncio.run(main())
PY
```

将输入换为 Spy S3 并使用 120089、matched_season=None，可观察 3→1；换为 JoJo 示例和 45790、matched_season=6，应观察 None→6。后两者需同步调整断言，不能共享错误预期。

### 4.3 清单逐项纯解析复现

以下只读文本，不读取文本中指向的媒体。它输出所有 305 个视频名的解析结果，用行号回查附录。

```bash
PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
import re
from pathlib import Path
from backend.parser import parse_file
count = 0
for line_no, line in enumerate(Path('unriad.output').read_text().splitlines(), 1):
    m = re.match(r'((?:│   |    )*)(?:├── |└── )(.*)', line)
    if not m or Path(m[2]).suffix.lower() not in {'.mkv','.mp4','.avi','.ts','.m2ts','.webm'}:
        continue
    count += 1
    p = parse_file(m[2])
    print(line_no, p.raw_filename, p.detected_title, p.season, p.episode)
assert count == 305  # 仅针对本次清单；清单改变后应审阅差异
PY
```

完整回放方法：按附录路径组成隔离 `BatchTriageJob`；清单 `Season 1` 子项归于其作品 batch；注入 2.2 表中本次查询的候选，未记录的 query 必须报错，不能默认为空。调用真实 `tmdb_async_resolve`，再向真实 `compute_target_plan` 传入由文件名字符串组成的 video stems 映射。此次已对 126+2 个输入执行，使用 confirm 模式。**它不包含 watcher 的目录发现/在线旧 override，不能声称等同完整部署验收。**

### 4.4 TMDB 候选与日志观察

- 安全读取凭据到内存，不能 print 配置全文、env、认证头、完整请求 URL。现有 `tmdb.py` 异常输出可能包含 URL；在线探针应屏蔽原始异常正文，只记录异常类和 HTTP 状态。
- 对每个 query 记录：原始文件名、清洗前后标题、目录 fallback query、候选 ID/name/original_name、年份、语言、各相似度分量、国家/类型加分、season_count、matched_season、最终分数和候选间差距。
- 同时记录 parser flags（当前是内部局部变量，必要时在调试器观察）、显式 season、TMDB season、配置/override 来源、effective title/season/episode、目标路径及 mode。
- 对 JoJo 使用 zh-CN/zh-HK/en-US 三种详情核验同一 ID；对中文标题同时比 `details.name`；对 Re:Zero 保存所选 episode order 及查询日期。
- 现有日志只记录解析查询、最高分名称和最终名称，缺少选中 ID、季来源、候选差距。建议在未来修复中补充这些结构化字段，复用日志设施，不引入新日志框架。

### 4.5 本次执行的测试及禁止执行的入口

已执行：

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest \
  backend/tests/test_parser.py backend/tests/test_tmdb_steel_ball_run.py \
  -q -p no:cacheprovider
# 76 passed in 0.15s
```

没有调用 `process_directory`、`find_all_anime_dirs`、真实 `process_dir_event`、`start_watcher`、`POST /api/scan`、confirm、reset_env.py 或任何 triage 执行函数。特别是 `triage._execute_triage_job_sync` 中 cleanup 的 `shutil.rmtree` 未受 dry_run 保护，**不能用 execute(..., dry_run=True) 当作本任务的安全预览**；用纯 planner 即可。该危险行为仅阅读记录，本次不修复。

## 5. 建议修复批次与涉及模块

| 批次 | 修改范围（未来执行） | 结果与验收 | 前置依赖 |
|---|---|---|---|
| A P1 | `watcher.tmdb_async_resolve`、`models.BatchTriageJob` 季来源/优先级；必要的最小数据字段 | V2=24 个 S2，S3=13 个 S3；V1 不回归；JoJo 无显式季可取 S6；人工配置语义保留 | 先写覆盖默认值覆盖的失败回归；明确冲突处理 |
| B P1 | `parser` 技术标签/年份清洗、`watcher` 目录查询构建 | U1 的 5 个变体与 U2 的 23 个英文变体同 ID；目录 query 不是 7³ACG/编码标签；不破坏正式数字标题 | 可独立于 A；无需新转译依赖 |
| C P1 | `parser` 平台标签、`tmdb._search_once` 本地化 name 评分 | B1 的 12 个文件输出规范标题；B2 精确中文 name 不再只有国家/类型加分；同名异作不误收 | 保留消歧负例，不全局降低阈值 |
| D P1 | `watcher.process_dir_event` / 异步回写、队列 override 来源 | 刷新保留人工 title/season/episode；旧自动结果能显式失效；异步结果不覆盖较新的人工选择 | 与 A 的来源定义一致；不自动清空已有队列 |
| E P2 | 多季 batch 的队列边界、冲突检测、`naming` 与 preview 一致性 | 同名 E01 不同季不互撞；混季批次不静默使用首个季 | 先补在线混季样例，选择最小可行批次拆分方案 |
| F 后续人工收尾 | 当前 test 的既有队列、原始名称保留及必要重匹配 | 重新取得只读快照比较；只对确认身份的旧 JoJo 项提出更新 | 当前队列安全快照到位，代码修复验收完成；**本次不改状态/媒体** |

Re:Zero 默认顺序不安排“减 25”修复。展示季标题若有明确产品需求再加入，当前正确系列标题不应被替换。不要因本计划一次性重构整个 parser/TMDB 层。

## 6. 回归测试方案

使用已有 pytest/AsyncMock 模式，不增加依赖；所有网络返回固定 fixture，所有文件访问用替身或临时合成数据。不要让测试导入 `backend.main` 的 lifespan 启动真实 watcher；API 测试必须注入隔离 config/queue 并屏蔽 watcher 和执行器。

| 用例 | 测试位置建议 | 必须断言 |
|---|---|---|
| Vinland S02E01–24、S1 对照 01–24；Spy S3 01–13 | `test_parser.py` + `test_watcher_tmdb.py` + `test_naming.py` | parsed 正确；TMDB matched_season=None 时显式季保留；规范标题正确；全体路径季集正确；Vinland 两季无同目标路径 |
| 无显式季的 JoJo 01/02、候选 60862/45790/336466 | 扩展 `test_tmdb_steel_ball_run.py` | 正确系列 ID=45790、matched_season=6、最终系列 name；不要仅测季号；含 OVA 负例、候选顺序打乱、目录 fallback、候选缺失需人工确认 |
| JoJo 中/英季名、简体/繁体系列名 | 同上 | 模拟 zh-CN 与默认语言返回不同详情；系列 name 与 season name 分开；`(2026)` 不被误作系列名 |
| Uma 五个罗马字输入与英文对照 | `test_parser.py`、`test_watcher_tmdb.py` | `2025 - .` 不污染查询，技术括号完整处理，正确 S1/E17、18、19、22、23；目录 query 不等于 `7³ACG` |
| Baha 12 项及 clean 中文 query | `test_parser.py`、TMDB 测试 | 标签不进入 effective title；alternative_titles 无中文时，精确本地化 name 仍能匹配；不靠降低阈值通过 |
| Re:Zero [26]、[50END]、[26-50END] 目录、SP | 解析/命名测试 | 默认顺序保持 S01E26–50，目录区间不是 episode；SP 不当成主篇；更换编号方案必须显式映射 |
| override 优先级及异步时序 | `test_queue_service.py` / `test_watcher_tmdb.py` | 人工季标题不被自动默认值覆盖；刷新保留 season/episode；TMDB 请求期间编辑标题，结果返回不抹掉编辑 |
| 多季同集号 | 模型/命名测试 | S01E01 和 S02E01 不算同季重复，不共享错误 stem；按所选批次策略输出或要求确认 |
| 防止清洗过度 | 解析参数化测试 | 正式标题内数字/年份/罗马数字/括号不无条件剥离；只移除已判定的技术或平台标签 |
| 预览与执行共同命名 | `test_naming.py` + 隔离 API 测试 | 比较纯 planner 与 preview；执行器仅 stub，断言未调用 rename/move/link/delete；auto/confirm 两模式均保持相同作品季集含义 |

现有测试缺口：JoJo 测试只提供一个 45790 候选，并且 mock 对两种语言都返回英文季详情；未覆盖 OVA 消歧、队列旧状态或 preview。现有 resolver 测试主要断言标题且使用 matched_season=1，不覆盖显式 S2/S3 被默认 1 覆盖。76 项通过不代表这些场景已修好。

验收完成条件：A–D 的确定性回归全部通过；当前 test 安全快照逐项补录原路径、raw parsed、候选、override 来源及 preview；四类问题输入达到预期且正确对照不回归；未核验项维持“待确认”。真实 rename/move/link 的验收属于之后另行授权的执行阶段，不是本计划编写任务。

## 附录 A：128 个重点回放输入与逐项结果

**路径是 fixture/示例的完整相对路径，不宣称对应媒体当前存在。** `unriad.output:L` 可以直接定位文本证据；J1 的两个路径为回放容器路径，第 2 集为合成，在线存在性未知。`当前`是隔离回放有效结果，`期望`遵循上文各例编号约定；R1 只对当前 TMDB 默认顺序成立。状态中的“已确认”也只限定回放。

| # | 状态/用例 | 输入相对路径（完整文件名） | 当前回放作品 / 季集 | 期望作品 / 季集 | 文本证据 |
|---|---|---|---|---|---|
| 1 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E03.mp4` | 穹廬下的魔女 [Baha] / S01E03 | 穹庐下的魔女 / S01E03 | `unriad.output:84` |
| 2 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E04.mp4` | 穹廬下的魔女 [Baha] / S01E04 | 穹庐下的魔女 / S01E04 | `unriad.output:85` |
| 3 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E05.mp4` | 穹廬下的魔女 [Baha] / S01E05 | 穹庐下的魔女 / S01E05 | `unriad.output:86` |
| 4 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E06.mp4` | 穹廬下的魔女 [Baha] / S01E06 | 穹庐下的魔女 / S01E06 | `unriad.output:87` |
| 5 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E07.mp4` | 穹廬下的魔女 [Baha] / S01E07 | 穹庐下的魔女 / S01E07 | `unriad.output:88` |
| 6 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E08.mp4` | 穹廬下的魔女 [Baha] / S01E08 | 穹庐下的魔女 / S01E08 | `unriad.output:89` |
| 7 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E09.mp4` | 穹廬下的魔女 [Baha] / S01E09 | 穹庐下的魔女 / S01E09 | `unriad.output:90` |
| 8 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E10.mp4` | 穹廬下的魔女 [Baha] / S01E10 | 穹庐下的魔女 / S01E10 | `unriad.output:91` |
| 9 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E11.mp4` | 穹廬下的魔女 [Baha] / S01E11 | 穹庐下的魔女 / S01E11 | `unriad.output:92` |
| 10 | 已确认 / B1 | `Bangumi/穹庐下的魔女/Season 1/穹廬下的魔女 [Baha] S01E12.mp4` | 穹廬下的魔女 [Baha] / S01E12 | 穹庐下的魔女 / S01E12 | `unriad.output:93` |
| 11 | 已确认 / B1 | `Bangumi/穹庐下的魔女/穹廬下的魔女 [Baha] S01E01.mp4` | 穹廬下的魔女 [Baha] / S01E01 | 穹庐下的魔女 / S01E01 | `unriad.output:94` |
| 12 | 已确认 / B1 | `Bangumi/穹庐下的魔女/穹廬下的魔女 [Baha] S01E02.mp4` | 穹廬下的魔女 [Baha] / S01E02 | 穹庐下的魔女 / S01E02 | `unriad.output:95` |
| 13 | 已确认 / U1 | `BangumiCollection/[BDrip] Uma Musume Shinderera Gurei S01 [7³ACG]/Uma Musume Shinderera Gurei 2025 S01E17-[1080p][BDRIP][x265.OPUS].mkv` | Uma Musume Shinderera Gurei 2025 - . / S01E17 | 赛马娘 芦毛灰姑娘 / S01E17 | `unriad.output:102` |
| 14 | 已确认 / U1 | `BangumiCollection/[BDrip] Uma Musume Shinderera Gurei S01 [7³ACG]/Uma Musume Shinderera Gurei 2025 S01E18-[1080p][BDRIP][x265.OPUS].mkv` | Uma Musume Shinderera Gurei 2025 - . / S01E18 | 赛马娘 芦毛灰姑娘 / S01E18 | `unriad.output:103` |
| 15 | 已确认 / U1 | `BangumiCollection/[BDrip] Uma Musume Shinderera Gurei S01 [7³ACG]/Uma Musume Shinderera Gurei 2025 S01E19-[1080p][BDRIP][x265.OPUS].mkv` | Uma Musume Shinderera Gurei 2025 - . / S01E19 | 赛马娘 芦毛灰姑娘 / S01E19 | `unriad.output:104` |
| 16 | 已确认 / U1 | `BangumiCollection/[BDrip] Uma Musume Shinderera Gurei S01 [7³ACG]/Uma Musume Shinderera Gurei 2025 S01E22-[1080p][BDRIP][x265.OPUS].mkv` | Uma Musume Shinderera Gurei 2025 - . / S01E22 | 赛马娘 芦毛灰姑娘 / S01E22 | `unriad.output:105` |
| 17 | 已确认 / U1 | `BangumiCollection/[BDrip] Uma Musume Shinderera Gurei S01 [7³ACG]/Uma Musume Shinderera Gurei 2025 S01E23-[1080p][BDRIP][x265.OPUS].mkv` | Uma Musume Shinderera Gurei 2025 - . / S01E23 | 赛马娘 芦毛灰姑娘 / S01E23 | `unriad.output:106` |
| 18 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E01-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E01 | 冰海战记 / S02E01 | `unriad.output:123` |
| 19 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E02-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E02 | 冰海战记 / S02E02 | `unriad.output:124` |
| 20 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E03-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E03 | 冰海战记 / S02E03 | `unriad.output:125` |
| 21 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E04-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E04 | 冰海战记 / S02E04 | `unriad.output:126` |
| 22 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E05-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E05 | 冰海战记 / S02E05 | `unriad.output:127` |
| 23 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E06-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E06 | 冰海战记 / S02E06 | `unriad.output:128` |
| 24 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E07-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E07 | 冰海战记 / S02E07 | `unriad.output:129` |
| 25 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E08-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E08 | 冰海战记 / S02E08 | `unriad.output:130` |
| 26 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E09-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E09 | 冰海战记 / S02E09 | `unriad.output:131` |
| 27 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E10-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E10 | 冰海战记 / S02E10 | `unriad.output:132` |
| 28 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E11-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E11 | 冰海战记 / S02E11 | `unriad.output:133` |
| 29 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E12-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E12 | 冰海战记 / S02E12 | `unriad.output:134` |
| 30 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E13-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E13 | 冰海战记 / S02E13 | `unriad.output:135` |
| 31 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E14-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E14 | 冰海战记 / S02E14 | `unriad.output:136` |
| 32 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E15-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E15 | 冰海战记 / S02E15 | `unriad.output:137` |
| 33 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E16-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E16 | 冰海战记 / S02E16 | `unriad.output:138` |
| 34 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E17-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E17 | 冰海战记 / S02E17 | `unriad.output:139` |
| 35 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E18-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E18 | 冰海战记 / S02E18 | `unriad.output:140` |
| 36 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E19-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E19 | 冰海战记 / S02E19 | `unriad.output:141` |
| 37 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E20-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E20 | 冰海战记 / S02E20 | `unriad.output:142` |
| 38 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E21-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E21 | 冰海战记 / S02E21 | `unriad.output:143` |
| 39 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E22-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E22 | 冰海战记 / S02E22 | `unriad.output:144` |
| 40 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E23-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E23 | 冰海战记 / S02E23 | `unriad.output:145` |
| 41 | 已确认 / V2 | `[BDrip] Vinland Saga S02 [7³ACG]/Vinland Saga S02E24-[1080p][BDRIP][x265.FLAC].mkv` | 冰海战记 / S01E24 | 冰海战记 / S02E24 | `unriad.output:146` |
| 42 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 01 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E01 | 冰海战记 / S01E01 | `unriad.output:148` |
| 43 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 02 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E02 | 冰海战记 / S01E02 | `unriad.output:149` |
| 44 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 03 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E03 | 冰海战记 / S01E03 | `unriad.output:150` |
| 45 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 04 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E04 | 冰海战记 / S01E04 | `unriad.output:151` |
| 46 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 05 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E05 | 冰海战记 / S01E05 | `unriad.output:152` |
| 47 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 06 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E06 | 冰海战记 / S01E06 | `unriad.output:153` |
| 48 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 07 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E07 | 冰海战记 / S01E07 | `unriad.output:154` |
| 49 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 08 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E08 | 冰海战记 / S01E08 | `unriad.output:155` |
| 50 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 09 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E09 | 冰海战记 / S01E09 | `unriad.output:156` |
| 51 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 10 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E10 | 冰海战记 / S01E10 | `unriad.output:157` |
| 52 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 11 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E11 | 冰海战记 / S01E11 | `unriad.output:158` |
| 53 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 12 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E12 | 冰海战记 / S01E12 | `unriad.output:159` |
| 54 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 13 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E13 | 冰海战记 / S01E13 | `unriad.output:160` |
| 55 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 14 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E14 | 冰海战记 / S01E14 | `unriad.output:161` |
| 56 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 15 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E15 | 冰海战记 / S01E15 | `unriad.output:162` |
| 57 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 16 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E16 | 冰海战记 / S01E16 | `unriad.output:163` |
| 58 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 17 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E17 | 冰海战记 / S01E17 | `unriad.output:164` |
| 59 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 18 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E18 | 冰海战记 / S01E18 | `unriad.output:165` |
| 60 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 19 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E19 | 冰海战记 / S01E19 | `unriad.output:166` |
| 61 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 20 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E20 | 冰海战记 / S01E20 | `unriad.output:167` |
| 62 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 21 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E21 | 冰海战记 / S01E21 | `unriad.output:168` |
| 63 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 22 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E22 | 冰海战记 / S01E22 | `unriad.output:169` |
| 64 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 23 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E23 | 冰海战记 / S01E23 | `unriad.output:170` |
| 65 | 正确对照 / V1 | `[BeanSub&LoliHouse] Vinland Saga [WebRip 1080p HEVC-10bit AAC ASSx2]/[BeanSub&LoliHouse] Vinland Saga - 24 [WebRip 1080p HEVC-10bit AAC ASSx2].mkv` | 冰海战记 / S01E24 | 冰海战记 / S01E24 | `unriad.output:171` |
| 66 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 01 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E01 | 赛马娘 芦毛灰姑娘 / S01E01 | `unriad.output:416` |
| 67 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 02 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E02 | 赛马娘 芦毛灰姑娘 / S01E02 | `unriad.output:417` |
| 68 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 03 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E03 | 赛马娘 芦毛灰姑娘 / S01E03 | `unriad.output:418` |
| 69 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 04 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E04 | 赛马娘 芦毛灰姑娘 / S01E04 | `unriad.output:419` |
| 70 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 05 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E05 | 赛马娘 芦毛灰姑娘 / S01E05 | `unriad.output:420` |
| 71 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 06 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E06 | 赛马娘 芦毛灰姑娘 / S01E06 | `unriad.output:421` |
| 72 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 07 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E07 | 赛马娘 芦毛灰姑娘 / S01E07 | `unriad.output:422` |
| 73 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 08 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E08 | 赛马娘 芦毛灰姑娘 / S01E08 | `unriad.output:423` |
| 74 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 09 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E09 | 赛马娘 芦毛灰姑娘 / S01E09 | `unriad.output:424` |
| 75 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 10 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E10 | 赛马娘 芦毛灰姑娘 / S01E10 | `unriad.output:425` |
| 76 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 11 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E11 | 赛马娘 芦毛灰姑娘 / S01E11 | `unriad.output:426` |
| 77 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 12 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E12 | 赛马娘 芦毛灰姑娘 / S01E12 | `unriad.output:427` |
| 78 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 13 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E13 | 赛马娘 芦毛灰姑娘 / S01E13 | `unriad.output:428` |
| 79 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 14 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E14 | 赛马娘 芦毛灰姑娘 / S01E14 | `unriad.output:429` |
| 80 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 15 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E15 | 赛马娘 芦毛灰姑娘 / S01E15 | `unriad.output:430` |
| 81 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 16 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E16 | 赛马娘 芦毛灰姑娘 / S01E16 | `unriad.output:431` |
| 82 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 17 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E17 | 赛马娘 芦毛灰姑娘 / S01E17 | `unriad.output:432` |
| 83 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 18 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E18 | 赛马娘 芦毛灰姑娘 / S01E18 | `unriad.output:433` |
| 84 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 19 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E19 | 赛马娘 芦毛灰姑娘 / S01E19 | `unriad.output:434` |
| 85 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 20 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E20 | 赛马娘 芦毛灰姑娘 / S01E20 | `unriad.output:435` |
| 86 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 21 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E21 | 赛马娘 芦毛灰姑娘 / S01E21 | `unriad.output:436` |
| 87 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 22 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E22 | 赛马娘 芦毛灰姑娘 / S01E22 | `unriad.output:437` |
| 88 | 正确对照 / U2 | `[LoliHouse] Uma Musume Cinderella Gray [WebRip 1080p HEVC-10bit AAC SRTx2]/[LoliHouse] Uma Musume Cinderella Gray - 23 [WebRip 1080p HEVC-10bit AAC SRTx2].mkv` | 赛马娘 芦毛灰姑娘 / S01E23 | 赛马娘 芦毛灰姑娘 / S01E23 | `unriad.output:438` |
| 89 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [01][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E01 | 间谍过家家 / S03E01 | `unriad.output:441` |
| 90 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [02][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E02 | 间谍过家家 / S03E02 | `unriad.output:442` |
| 91 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [03][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E03 | 间谍过家家 / S03E03 | `unriad.output:443` |
| 92 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [04][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E04 | 间谍过家家 / S03E04 | `unriad.output:444` |
| 93 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [05][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E05 | 间谍过家家 / S03E05 | `unriad.output:445` |
| 94 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [06][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E06 | 间谍过家家 / S03E06 | `unriad.output:446` |
| 95 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [07][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E07 | 间谍过家家 / S03E07 | `unriad.output:447` |
| 96 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [08][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E08 | 间谍过家家 / S03E08 | `unriad.output:448` |
| 97 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [09][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E09 | 间谍过家家 / S03E09 | `unriad.output:449` |
| 98 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [10][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E10 | 间谍过家家 / S03E10 | `unriad.output:450` |
| 99 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [11][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E11 | 间谍过家家 / S03E11 | `unriad.output:451` |
| 100 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [12][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E12 | 间谍过家家 / S03E12 | `unriad.output:452` |
| 101 | 已确认 / S3 | `[Sakurato] Spy x Family S3 [HEVC-10bit 1080p AAC][CHS&CHT]/[Sakurato] Spy x Family S3 [13][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | 间谍过家家 / S01E13 | 间谍过家家 / S03E13 | `unriad.output:453` |
| 102 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E26 | Re：从零开始的异世界生活 / S01E26 | `unriad.output:481` |
| 103 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][27][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E27 | Re：从零开始的异世界生活 / S01E27 | `unriad.output:482` |
| 104 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][28][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E28 | Re：从零开始的异世界生活 / S01E28 | `unriad.output:483` |
| 105 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][29][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E29 | Re：从零开始的异世界生活 / S01E29 | `unriad.output:484` |
| 106 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][30][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E30 | Re：从零开始的异世界生活 / S01E30 | `unriad.output:485` |
| 107 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][31][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E31 | Re：从零开始的异世界生活 / S01E31 | `unriad.output:486` |
| 108 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][32][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E32 | Re：从零开始的异世界生活 / S01E32 | `unriad.output:487` |
| 109 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][33][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E33 | Re：从零开始的异世界生活 / S01E33 | `unriad.output:488` |
| 110 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][34][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E34 | Re：从零开始的异世界生活 / S01E34 | `unriad.output:489` |
| 111 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][35][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E35 | Re：从零开始的异世界生活 / S01E35 | `unriad.output:490` |
| 112 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][36][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E36 | Re：从零开始的异世界生活 / S01E36 | `unriad.output:491` |
| 113 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][37][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E37 | Re：从零开始的异世界生活 / S01E37 | `unriad.output:492` |
| 114 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][38][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E38 | Re：从零开始的异世界生活 / S01E38 | `unriad.output:493` |
| 115 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][39][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E39 | Re：从零开始的异世界生活 / S01E39 | `unriad.output:494` |
| 116 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][40][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E40 | Re：从零开始的异世界生活 / S01E40 | `unriad.output:495` |
| 117 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][41][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E41 | Re：从零开始的异世界生活 / S01E41 | `unriad.output:496` |
| 118 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][42][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E42 | Re：从零开始的异世界生活 / S01E42 | `unriad.output:497` |
| 119 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][43][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E43 | Re：从零开始的异世界生活 / S01E43 | `unriad.output:498` |
| 120 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][44][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E44 | Re：从零开始的异世界生活 / S01E44 | `unriad.output:499` |
| 121 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][45][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E45 | Re：从零开始的异世界生活 / S01E45 | `unriad.output:500` |
| 122 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][46][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E46 | Re：从零开始的异世界生活 / S01E46 | `unriad.output:501` |
| 123 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][47][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E47 | Re：从零开始的异世界生活 / S01E47 | `unriad.output:502` |
| 124 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][48][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E48 | Re：从零开始的异世界生活 / S01E48 | `unriad.output:503` |
| 125 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][49][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E49 | Re：从零开始的异世界生活 / S01E49 | `unriad.output:504` |
| 126 | 正确对照（默认顺序） / R1 | `[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][26-50END][BDRip 1080p AVC AAC][CHS]/[hyakuhuyu][Re Zero kara Hajimeru Isekai Seikatsu][50END][BDRip 1080p AVC AAC][CHS].mp4` | Re：从零开始的异世界生活 / S01E50 | Re：从零开始的异世界生活 / S01E50 | `unriad.output:505` |
| 127 | 正确对照 / J1 | `Bangumi/飙马野郎 JOJO的奇妙冒险/[Sakurato] Steel Ball Run：JoJo no Kimyou na Bouken [01][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | JOJO的奇妙冒险 / S06E01 | JOJO的奇妙冒险 / S06E01 | 用户示例 |
| 128 | 正确对照 / J1 | `Bangumi/飙马野郎 JOJO的奇妙冒险/[Sakurato] Steel Ball Run：JoJo no Kimyou na Bouken [02][HEVC-10bit 1080p AAC][CHS&CHT].mkv` | JOJO的奇妙冒险 / S06E02 | JOJO的奇妙冒险 / S06E02 | 合成第二集；非当前文件证据 |

## 附录 B：本次工作区证据校验值

这些 SHA-256 用于识别实际受审计内容（包括已有未提交修改），不替代在线部署版本核验。临时回放结果存放于 `/tmp`，可能被清理；核心结论及逐项结果已完整写入本文，不依赖临时文件才能阅读。

| 文件 | SHA-256 |
|---|---|
| `unriad.output` | `0fa806a392a7f8875497ebff696cafcbde73a5e6ae04f2d3364897bb030dcd7d` |
| `backend/parser.py` | `91e7efe926269ae397956b4b5061f7e0437056ac43db88acc2e1fbbd7499effb` |
| `backend/tmdb.py` | `a86fa48ec6fd2b5ddd938c721faffd71fadd8dc8676bf6be4eddb77171ba31af` |
| `backend/watcher.py` | `7b71f602d9a0e913c941d68a8719ab50a42f7eb28794e57c40d08671486bee2c` |
| `backend/models.py` | `a6726b062a99af8eafad369ae192446e0b73357cc122f45fc74e20b6dcf97fda` |
| `backend/domain/naming.py` | `95bb8b1edfae0dd6d2fe1a61da7edbeda63dfd1d9c17709054950456f59139db` |
| `backend/tests/test_tmdb_steel_ball_run.py` | `385c526743583d92682a8b06372c2b7906c2d9a733613b14e59a51d559b91332` |
