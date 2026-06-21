# AnimeRenamer v2 — 配置与部署指南

> **阅读顺序：先 Part B（了解你的环境）→ 再 Part A（填配置）**

---

## 你的环境概况（已从 unriad.output 提取）

| 项目 | 路径 |
|---|---|
| 下载目录 | `/mnt/user/hentaidisk/Downloads` |
| 动漫存储目录 | `/mnt/user/hentaidisk/video/anime` |
| Jellyfin 追番目录 | `/mnt/user/hentaidisk/video/link/Bangumi` |
| Jellyfin TV收藏目录 | `/mnt/user/hentaidisk/video/link/anime/动漫` |
| Jellyfin 电影目录 | `/mnt/user/hentaidisk/video/link/anime/动画电影` |
| PUID | `99` (nobody) |
| PGID | `100` (users) |

---

## Part B：关键问题解答

### B1. PUID / PGID 确认结果

你用 root 登录，`id` 返回 `uid=0`，这是 root，**不是文件实际属主**。

执行 `id nobody` 的结果：**`uid=99(nobody) gid=100(users)`**

✅ **已确认：`PUID=99, PGID=100`**（Unraid 标准 nobody 用户）

实际输出：
```bash
root@hentaidisk:/mnt/user/hentaidisk/Downloads# id nobody
uid=99(nobody) gid=100(users) groups=100(users),98(nobody)
```

---

### B2. 关于 `.ass` 字幕文件

你的下载中还有 `.ass` 字幕文件需要跟视频文件一起被处理。

**当前行为**：watcher 只监听 `*.mkv / *.mp4 / *.avi`，`.ass` 不会被触发。

**解决方案（后续 Gemini 任务）**：
- 在 watcher 里把识别到的视频文件对应的 `.ass` 文件也一起搬运
- 规则：视频文件 `[SubsPlease] Anime - 01.mkv` → 找同目录下 `*.ass` 里包含相同 episode 编号的一起 hardlink

---

### B3. 关于非动画文件的过滤

你的下载目录里有很多不是动画的文件：
- `直拍.mp4`、`马儿跳——使用Clipchamp制作.mp4`（个人视频）
- `HMN-239-HD/`（其他内容）
- `_Umapyoi-Densetsu.mp4`（音乐视频）

**当前行为**：这些文件会进入队列但识别置信度低（<0.65），**不会自动执行**（confirm 模式）。

**建议**：在 `series_config.yaml` 里加一个 `watch_subdir` 配置，让 watcher 只监控 `Downloads/Bangumi/` 子目录而不是整个 Downloads 根目录，这样就自然过滤掉了。

---

### B4. 动漫存储目录的命名规范

你有两种混存的风格：
- **旧风格（不喜欢）**：`/video/anime/全金属狂潮/[01] [020115] フルメタル・パニック!/`
- **新风格（喜欢）**：`/video/anime/为美好的世界献上祝福！/Season 3/`

本工具**只产出新风格**：
```
/video/anime/{tmdb_name}/Season {N}/
```

旧风格的库保持不动，不会被修改。新入库的内容统一用新风格。

---

### B5. 真实文件识别报告

用你下载目录里的真实文件名跑 parser 的结果：

| 统计 | 数量 |
|---|---|
| 总文件数 | 76 |
| ✅ 成功识别（置信度≥0.7） | 68 |
| ❌ 无法识别集数 | 8 |
| 💥 Parser 崩溃（bug） | 2 |

**需要你配置 alias 的番剧：**

| 原始文件名中的名称 | 问题 | 建议 tmdb_name |
|---|---|---|
| `Toaru Kagaku no Railgun T` | 季数未知（需在 config 里指定 season=3） | `Toaru Kagaku no Railgun` |
| `Horimiya` | 已识别，需确认 | `Horimiya` |
| `Chainsaw Man` | 已识别（Compilation特别版） | `Chainsaw Man` |
| `リトルウィッチアカデミア` | OVA，无集数，需手动 | `Little Witch Academia` |
| `劇場版 リトルウィッチアカデミア` | 电影，需手动 | 放电影目录 |
| `Uma Musume` 电影版 | 电影，无集数 | 放电影目录 |

**发现的 Parser Bug（需要 Gemini 修复）：**

1. `Frieren Beyond Journeys End S02E01.mkv` → `season=0` → Pydantic `ge=1` 崩溃
   - 原因：`S02` 被解析为 season=2，但还有 `E05.10.11.12` 多集格式也触发了
   - 根因是 `Panty.and.Stocking.with.Garterbelt.S02E05.10.11.12` 的多集格式解析失败后季数出错

2. 解决方案：parser 内部捕获 `season=0` 时改为 `season=None`

---

## Part A：配置文件（已预填你的信息）

### A1. `config/series_config.yaml` 完整版

直接把以下内容覆盖到 `config/series_config.yaml`：

```yaml
settings:
  tmdb_api_key: "5e97c1d152a2609f6e208a52081b00f0"
  confidence_threshold: 0.85
  default_mode: confirm
  # 下载监控目录（建议只监控 Bangumi 子目录，过滤非动画文件）
  download_dir: "/mnt/user/hentaidisk/Downloads/Bangumi"
  storage_dir: "/mnt/user/hentaidisk/video/anime"
  # 新番追番目录（当季、每周更新）
  jellyfin_airing_dir: "/mnt/user/hentaidisk/video/link/Bangumi"
  # 补番收藏目录（TV动画）
  jellyfin_collect_dir: "/mnt/user/hentaidisk/video/link/anime/动漫"
  # 电影（目前需手动，待后续实现电影支持）
  # jellyfin_movie_dir: "/mnt/user/hentaidisk/video/link/anime/动画电影"

series:
  # ===== 当季追番（auto模式，全自动）=====

  # 凉宫春日的忧郁（2009年完整版，补番）
  Suzumiya Haruhi no Yuuutsu:
    mode: confirm
    tmdb_name: The Melancholy of Haruhi Suzumiya
    tmdb_id: 46260
    season: 1
    aliases:
      - Suzumiya Haruhi no Yuuutsu
      - 凉宫春日的忧郁
      - 涼宮ハルヒの憂鬱

  # 某科学的超电磁炮T（第三季，补番）
  Toaru Kagaku no Railgun:
    mode: confirm
    tmdb_name: A Certain Scientific Railgun
    tmdb_id: 38892
    season: 3
    aliases:
      - Toaru Kagaku no Railgun T
      - 某科学的超电磁炮T
      - とある科学の超電磁砲T

  # Horimiya（补番）
  Horimiya:
    mode: confirm
    tmdb_name: Horimiya
    tmdb_id: 115230
    season: 1
    aliases:
      - Horimiya
      - 堀与宫村

  # 电锯人 Chainsaw Man Compilation（补番特别版）
  Chainsaw Man:
    mode: confirm
    tmdb_name: Chainsaw Man
    tmdb_id: 114410
    season: 1
    aliases:
      - Chainsaw Man
      - Chainsaw Man - The Compilation
      - 电锯人

  # 小魔女学园TV版（2017）
  Little Witch Academia:
    mode: confirm
    tmdb_name: Little Witch Academia
    tmdb_id: 66940
    season: 1
    aliases:
      - Little Witch Academia
      - リトルウィッチアカデミア
      - 小魔女学园

  # ===== 补充你自己的番剧 =====
  # 格式：
  # 你想要的存储目录名:
  #   mode: auto       # 当季新番用 auto；补番用 confirm
  #   tmdb_name: TMDB上的英文名（在 themoviedb.org/tv/XXXXX 里找）
  #   tmdb_id: 数字ID
  #   season: 1
  #   aliases:
  #     - 字幕组文件名里出现的名称1
  #     - 名称2
```

---

### A2. `docker-compose.yml` 完整版

直接覆盖 `docker-compose.yml`：

```yaml
version: "3.8"
services:
  anime-triage:
    build: .
    container_name: anime-triage
    ports:
      - "8765:8765"
    environment:
      - PUID=99
      - PGID=100
      - TMDB_API_KEY=5e97c1d152a2609f6e208a52081b00f0
    volumes:
      # 只挂载 Bangumi 子目录，过滤非动画内容
      - /mnt/user/hentaidisk/Downloads/Bangumi:/downloads
      # 动漫存储目录（整理后的最终位置）
      - /mnt/user/hentaidisk/video/anime:/anime
      # Jellyfin 追番目录（当季新番 hardlink）
      - /mnt/user/hentaidisk/video/link/Bangumi:/jellyfin/airing
      # Jellyfin 收藏目录（补番 hardlink）
      - /mnt/user/hentaidisk/video/link/anime/动漫:/jellyfin/anime
      # 配置和日志（项目目录）
      - ./config:/app/config
      - ./logs:/app/logs
    restart: unless-stopped
```

---

### A3. 在 Unraid 上部署

```bash
# 1. 把项目放到 appdata
cd /mnt/user/appdata/
git clone <你的仓库地址> anime-triage
cd anime-triage

# 2. 配置已经预填好了，直接构建
docker-compose up -d --build

# 3. 查看日志
docker-compose logs -f anime-triage

# 4. 访问 WebUI
# http://你的NAS-IP:8765
```

---

## 待修复的 Bug（给 Gemini 的任务）

以下 Bug 需要修复后才能在真实环境跑通：

### Bug 4（parser）：season=0 导致崩溃

**文件**：`Frieren Beyond Journeys End S02E01.mkv`

**错误**：`ParsedAnime.season` 有 `ge=1` 约束，但 parser 在特定情况下返回 `season=0`

**修复**：在 `backend/parser.py` 内部，任何地方将 `season` 传入 `ParsedAnime` 之前，做检查：
```python
# 在 _parse_stem 函数里，构造 ParsedAnime 之前
if season == 0:
    season = None
```

**验证**：
```bash
python -c "
from backend.parser import parse_file
r = parse_file('Frieren Beyond Journeys End S02E01.mkv')
print(r.season, r.episode)  # 应该输出: 2 1
r2 = parse_file('Panty.and.Stocking.with.Garterbelt.S02E05.10.11.12.1080p.AMZN.WEB-DL.DUAL.DDP5.1.H.264-VARYG.mkv')
print(r2.season, r2.episode)  # 应该输出: 2 5 (多集格式取第一集)
"
```

### Bug 5（config 模型）：AppConfig 需新增字段

你实际有 5 个路径（下载、存储、追番、TV收藏、电影），但 `AppConfig` 目前只有 4 个。

需要在 `backend/config.py` 的 `AppConfig` 里**新增**：
```python
jellyfin_movie_dir: Path = Path("/jellyfin/movie")
```

---

## 快速 Checklist

- [x] 下载目录路径已确认：`/mnt/user/hentaidisk/Downloads`
- [x] 动漫存储路径已确认：`/mnt/user/hentaidisk/video/anime`
- [x] Jellyfin 三个目录已确认（追番/TV收藏/电影）
- [x] TMDB API Key 已填入
- [x] PUID=99, PGID=100（id nobody 已确认）
- [ ] Bug 修复：SxxExx parser + season=0 崩溃（GEMINI_TASK_2.md Task 1）
- [ ] 增强：双语 TMDB 搜索（GEMINI_TASK_2.md Task 2）
- [ ] 增强：非动画文件过滤（GEMINI_TASK_2.md Task 3）
- [ ] 配置：Railgun T alias 填入 series_config.yaml（GEMINI_TASK_2.md Task 4）
- [ ] `.ass` 字幕文件跟随处理（后续任务）
