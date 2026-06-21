# BUG FIX PLAN — AnimeRenamer v2

> This file is a task for Gemini. Fix all 5 bugs in order of priority.
> After each fix, run `curl -X POST http://localhost:8765/api/scan` and verify.
> The dev server is always running at `http://localhost:8765/` via:
> `uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload`

---

## BUG 1 🔴 — `[SRTx2]` residue in title (parser.py)

**Symptom:**
```
[LoliHouse] Chainsaw Man - The Compilation [WebRip 1080p HEVC-10bit AAC SRTx2]
→ detected_title = "Chainsaw Man - The Compilation [ SRTx2"
```

**Root cause:** `SRTx2`, `FLACx2`, `10bit`, `10-bit` are not in `_JUNK_TAGS`.
The `[` left over after stripping `SRTx2]` is also not cleaned up correctly.

**Fix in `/workspaces/anime_triage/backend/parser.py`:**

Add this as the **FIRST** entry in `_JUNK_TAGS` (before the existing resolution pattern,
around line 41). This whole-bracket pattern must go first so it fires before individual tag stripping:

```python
# Whole bracket blocks that are pure tech specs (contains any codec/resolution keyword)
re.compile(
    r"\[[^\]]*"
    r"(?:SRTx?\d*|FLACx?\d*|HEVC|AVC|1080p|720p|480p|BDRip|WebRip|WEB-DL|10.?bit)"
    r"[^\]]*\]",
    re.IGNORECASE,
),
```

Also add these two individual tag patterns after the existing audio codec block (after line 63):

```python
# Subtitle track count tags: SRTx2, ASSx2, PGSx2
re.compile(r"\b(?:SRT|ASS|PGS|SSA)x?\d*\b", re.IGNORECASE),
# Bit-depth tags: 10bit, 10-bit, 8bit
re.compile(r"\b\d+[-]?bit\b", re.IGNORECASE),
```

**Verify:** After fix, the Chainsaw Man folder's `detected_title` should be
`"Chainsaw Man - The Compilation"` with no trailing junk.

---

## BUG 2 🟠 — Directories with zero video files create a Job (watcher.py)

**Symptom:**
- `小魔女学园/` contains only `.rar` and subdirectories — no `.mkv` or `.mp4`
- Appears in pending queue with `confidence = 0.00` and `0 Eps`

**Fix in `/workspaces/anime_triage/backend/watcher.py`:**

In `process_directory()`, after the item-scanning loop (around line 84),
change the guard from:

```python
if not items:
    return None
```

to:

```python
video_count = sum(1 for it in items if it.is_video)
if not items or video_count == 0:
    return None
```

**Verify:** After fix, `小魔女学园` should NOT appear in `/api/pending`.

---

## BUG 3 🟠 — Non-anime root directories (e.g. JAV) enter the queue (watcher.py + main.py)

**Symptom:**
- `HMN-239-HD/` is at the Downloads root (not inside Bangumi/) — it is a JAV folder
- A Chinese-named mp4 inside fools the parser (conf 0.78) into treating it as anime

**Fix — two-part:**

**Part A: Add `strict` flag to `process_directory` in `/workspaces/anime_triage/backend/watcher.py`:**

Change signature:
```python
def process_directory(dir_path: Path, config, series_db, strict: bool = False) -> BatchTriageJob | None:
```

At the end of the function, before `return job`, add:
```python
if strict and job.confidence < 0.65:
    return None
```

**Part B: Pass `strict=True` for non-Bangumi dirs in `trigger_scan()` in `/workspaces/anime_triage/backend/main.py`:**

Change the scan loop from:
```python
dirs_to_scan = set()
download_dir = Path(config.download_dir)
if download_dir.exists():
    for child in download_dir.iterdir():
        if child.is_dir():
            if child.name in ["Bangumi", "BangumiCollection"]:
                for subchild in child.iterdir():
                    if subchild.is_dir():
                        dirs_to_scan.add(subchild)
            else:
                dirs_to_scan.add(child)

for d in dirs_to_scan:
    handler.process_dir_event(d)
```

to:
```python
dirs_to_scan: list[tuple[Path, bool]] = []
download_dir = Path(config.download_dir)
if download_dir.exists():
    for child in download_dir.iterdir():
        if child.is_dir():
            if child.name in ["Bangumi", "BangumiCollection"]:
                for subchild in child.iterdir():
                    if subchild.is_dir():
                        dirs_to_scan.append((subchild, False))  # trusted source
            else:
                dirs_to_scan.append((child, True))   # strict: must pass confidence gate

for d, strict in dirs_to_scan:
    handler.process_dir_event(d, strict=strict)
```

Also update `DownloadDirHandler.process_dir_event()` to accept and forward `strict`:

```python
def process_dir_event(self, dir_path: Path, strict: bool = False):
    ...
    job = process_directory(dir_path, self.config, self.series_db, strict=strict)
```

**Verify:** After fix, `HMN-239-HD` should NOT appear in `/api/pending`.

---

## ~~BUG 4~~ — CANCELLED: 赛马娘 season conflict is NOT a bug

**Investigation finding:**
```
赛马娘 芦毛灰姑娘 (2025)/Season 1/   → E01–E17  (two fansub groups, same season)
赛马娘 芦毛灰姑娘 第2部分/Season 1/  → E18–E23
```
The two directories are the **same Season 1**, downloaded in two batches from different
fansub groups. Episode ranges are completely non-overlapping — no conflict at all.
Confirming each job in sequence will correctly populate `anime/赛马娘 芦毛灰姑娘/Season 01/`
with E01–E23. No season number changes needed.

**Instead, implement FEATURE 6 below.**

---

## FEATURE 6 🟢 — Merge suggestion for split-batch same-season jobs

**Goal:** When two pending Jobs resolve to the **same title + same season** and have
**non-overlapping episode sets**, show a merge hint badge. This is informational only —
the user confirms each job separately, and they naturally write to the same target folder.

### Step 1: Add `episode_set` field to `/api/pending` response (`main.py`)

In `get_queue()`, inside the `res.append({...})` block, add:

```python
ep_set = sorted(set(
    it.parsed.episode
    for it in j.items
    if it.is_video and it.parsed and it.parsed.episode is not None
))
# ...inside the dict:
"episode_set": ep_set,
```

### Step 2: Detect merge candidates after building `res` (`main.py`)

After the `for j in queue.values()` loop, before `return res`, add:

```python
from collections import defaultdict
title_season_groups: dict[tuple, list[int]] = defaultdict(list)
for i, item in enumerate(res):
    key = (item["detected_title"], item["season"])
    title_season_groups[key].append(i)

for key, indices in title_season_groups.items():
    if len(indices) < 2:
        continue
    for i in range(len(indices)):
        for j_idx in range(i + 1, len(indices)):
            a, b = res[indices[i]], res[indices[j_idx]]
            set_a = set(a.get("episode_set", []))
            set_b = set(b.get("episode_set", []))
            if set_a and set_b and set_a.isdisjoint(set_b):
                combined = sorted(set_a | set_b)
                a["merge_suggestion"] = {
                    "merge_with_id": b["id"],
                    "merge_with_filename": b["original_filename"],
                    "combined_episodes": combined,
                }
                b["merge_suggestion"] = {
                    "merge_with_id": a["id"],
                    "merge_with_filename": a["original_filename"],
                    "combined_episodes": combined,
                }
```

### Step 3: Show merge badge in the pending card (`frontend/js/app.js`)

In the card HTML template, after the `card-detected` div, add:

```javascript
${item.merge_suggestion
  ? `<div class="merge-hint">
       <span class="merge-icon">🔗</span>
       <span>可与 <code>${escapeHtml(item.merge_suggestion.merge_with_filename)}</code> 合并</span>
       <span class="merge-eps">
         合并后 E${String(item.merge_suggestion.combined_episodes[0]).padStart(2,'0')}
         –E${String(item.merge_suggestion.combined_episodes[item.merge_suggestion.combined_episodes.length-1]).padStart(2,'0')}
       </span>
     </div>`
  : ''
}
```

### Step 4: Add CSS for merge badge (`frontend/css/style.css`)

```css
.merge-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  margin-top: 8px;
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 6px;
  font-size: 0.8rem;
  color: #a5b4fc;
}
.merge-hint code {
  font-size: 0.75rem;
  color: #c7d2fe;
  word-break: break-all;
}
.merge-eps {
  margin-left: auto;
  font-weight: 600;
  color: #818cf8;
  white-space: nowrap;
}
```

**Verify:** After scan, both 赛马娘 cards show a 🔗 indigo badge displaying `合并后 E01–E23`.

---


## BUG 5 🟡 — `/api/recent` uses file path as `id` instead of job id (main.py)

**Symptom:** `GET /api/recent` returns `"id": "[SweetSub] Horimiya ..."` (a path string)
instead of the numeric job id like `"id": "1782049271728"`.

**Fix in `/workspaces/anime_triage/backend/main.py`:**

1. Change the `history` list to store enriched dicts. Find `confirm_job()` (around line 103)
   and replace the `history.insert(0, res)` line:

```python
# REPLACE:
history.insert(0, res)

# WITH:
history.insert(0, {
    "job_id": job_id,
    "result": res,
    "title": job.effective_title,
})
```

2. Update `get_history()` (around line 147) to read the new dict format:

```python
@app.get("/api/recent")
async def get_history() -> list[dict[str, Any]]:
    res = []
    for entry in history:
        r = entry["result"]
        res.append({
            "id": entry["job_id"],
            "status": "done" if r.success else "error",
            "filename": Path(r.source_path).name if r.source_path else "Unknown",
            "title": entry.get("title", Path(r.dest_path).stem if r.dest_path else "Unknown"),
            "error_msg": r.error_msg,
            "mode": "auto",
            "confidence": 1.0,
            "timestamp": "Just now",
        })
    return res
```

Also update the type annotation of `history` at the top of `main.py` from
`history: list[TriageResult] = []` to `history: list[dict] = []`.

**Verify:** After confirming a job, `/api/recent` should show `"id": "1782..."` (numeric string).

---

## Final Verification Checklist

After ALL fixes, run:
```bash
python reset_env.py
curl -X POST http://localhost:8765/api/scan
sleep 5
curl -s http://localhost:8765/api/pending | python -c "
import json,sys
d=json.load(sys.stdin)
print('Total jobs:', len(d))
for j in d:
    print(j['original_filename'], '->', j['detected_title'], '| S', j['season'], '| conf', round(j['confidence'],2))
"
```

Confirm:
- [ ] Total jobs ≤ 14 (HMN-239-HD and 小魔女学园 are gone)
- [ ] Chainsaw Man title has NO `[ SRTx2` suffix
- [ ] 赛马娘 芦毛灰姑娘 第2部分 shows `season: 2`
- [ ] `/api/recent` (after a confirm) shows numeric `id`
