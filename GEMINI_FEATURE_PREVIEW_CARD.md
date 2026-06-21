# FEATURE PLAN — Expandable Rename Preview Card

> Task for Gemini. This is a **pure frontend + one backend endpoint** feature.
> Read the existing card template in `frontend/js/app.js` (function `renderPendingCard`, line ~135)
> and styles in `frontend/css/style.css` before starting.
>
> Server: `uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload`
> Test trigger: `curl -X POST http://localhost:8765/api/scan`

---

## Overview

Each pending card currently shows only the source directory and detected title.
We want users to be able to **click the card** to expand a full rename preview panel
showing every file inside — what it was called before, and what it will be called after.

**Final UI sketch:**

```
┌─────────────────────────────────────────────────────────────────┐
│  [CONFIRM]  S01  14 Eps                              38.2 GB    │
│                                                                  │
│  原始目录   Bangumi/赛马娘 芦毛灰姑娘 (2025)                      │
│  中文：赛马娘 芦毛灰姑娘  (blinking)                             │
│  ████████████████████░░  95%  excellent                         │
│  目标路径   .../anime/赛马娘 芦毛灰姑娘/Season 01                │
│                                                                  │
│  🔗 可与 赛马娘...第2部分 合并  合并后 E01–E23                    │
│                                            [展开预览 ▾]         │
│ ─────────────────────────────────────────────────────────────── │
│  ▼ 改名预览  (14 个文件)                                         │
│                                                                  │
│  旧文件名                              →  新文件名               │
│  ──────────────────────────────────────────────────────────     │
│  Umamusume Cinderella Gray[01]...mkv   →  赛马娘 S01E01.mkv    │
│  Umamusume Cinderella Gray[01]...mkv   →  赛马娘 S01E01.mkv    │  ← (sub same episode)
│  [OguriClub] Umamusume...[03]...mkv   →  赛马娘 S01E03.mkv    │
│  ...                                                             │
│                                                                  │
│  ── 以下文件不会改名（特典/Bonus，原样搬运）──────────────────── │
│  [SweetSub] Horimiya - NCED [BDRip...].mkv         (灰色)      │
│  [SweetSub] Horimiya - OPv1 [BDRip...].mkv         (灰色)      │
│                                                                  │
│       [✅ 确认]   [✏️ 编辑]   [⏭ 跳过]                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Backend — add `/api/pending/{job_id}/preview` endpoint

**File:** `/workspaces/anime_triage/backend/main.py`

Add a new GET endpoint that returns the full per-file rename plan for a job.
This mirrors the logic in `execute_triage_job()` (`triage.py`) but without
actually moving anything — it just computes the would-be filenames.

Add after the existing `confirm_job` route:

```python
@app.get("/api/pending/{job_id}/preview")
async def preview_job(job_id: str) -> dict:
    if job_id not in queue:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = queue[job_id]
    anime_name = job.effective_title
    season = job.effective_season
    season_str = f"{season:02d}"
    
    download_dir = Path(config.download_dir)
    storage_dir = Path(config.storage_dir)
    
    renamed = []   # files that will be renamed
    preserved = [] # files that will be kept as-is (extras/bonus)
    
    for it in job.items:
        source_file = download_dir / it.relative_path
        old_name = source_file.name
        
        episode = it.parsed.episode if it.parsed else None
        
        if episode is not None:
            ext = source_file.suffix.lower()
            new_name = f"{anime_name} S{season_str}E{episode:02d}{ext}"
            new_path = str(storage_dir / anime_name / f"Season {season_str}" / new_name)
            renamed.append({
                "old_name": old_name,
                "new_name": new_name,
                "new_path": new_path,
                "is_video": it.is_video,
                "episode": episode,
            })
        else:
            # Extra / bonus — preserved with original name
            if job.source_dir != ".":
                try:
                    rel = source_file.relative_to(download_dir / job.source_dir)
                except ValueError:
                    rel = Path(old_name)
            else:
                rel = Path(old_name)
            preserved.append({
                "old_name": str(rel),   # preserve subdirectory structure in name
                "is_video": it.is_video,
            })
    
    # Sort renamed by episode number
    renamed.sort(key=lambda x: (x["episode"], x["old_name"]))
    
    return {
        "job_id": job_id,
        "anime_name": anime_name,
        "season": season,
        "renamed": renamed,
        "preserved": preserved,
    }
```

---

## Step 2: Frontend — expandable preview panel

**File:** `/workspaces/anime_triage/frontend/js/app.js`

### 2a. Add expand toggle button to the card

In `renderPendingCard()`, locate the `card-target` block (the target path row).
**After** that div and the `card-detected-time` div, but **before** `card-actions`,
add:

```javascript
<button class="btn-expand-preview" data-id="${item.id}" onclick="togglePreview('${item.id}', this)">
  展开预览 ▾
</button>

<div class="rename-preview-panel" id="preview-${item.id}" style="display:none;">
  <div class="preview-loading">加载中...</div>
</div>
```

### 2b. Add `togglePreview()` function

Add this new function anywhere in `app.js`:

```javascript
async function togglePreview(jobId, btn) {
  const panel = document.getElementById(`preview-${jobId}`);
  const isOpen = panel.style.display !== 'none';
  
  if (isOpen) {
    panel.style.display = 'none';
    btn.textContent = '展开预览 ▾';
    return;
  }
  
  panel.style.display = 'block';
  btn.textContent = '收起预览 ▴';
  
  // Only fetch if not already loaded
  if (panel.dataset.loaded === 'true') return;
  
  try {
    const resp = await fetch(`${API_BASE}/pending/${jobId}/preview`);
    if (!resp.ok) throw new Error('Failed to load preview');
    const data = await resp.json();
    panel.innerHTML = renderPreviewPanel(data);
    panel.dataset.loaded = 'true';
  } catch (e) {
    panel.innerHTML = `<div class="preview-error">预览加载失败: ${e.message}</div>`;
  }
}
```

### 2c. Add `renderPreviewPanel()` function

```javascript
function renderPreviewPanel(data) {
  const renamedRows = data.renamed.map(f => `
    <tr class="preview-row${f.is_video ? '' : ' preview-sub'}">
      <td class="preview-old">${escapeHtml(f.old_name)}</td>
      <td class="preview-arrow">→</td>
      <td class="preview-new">${escapeHtml(f.new_name)}</td>
    </tr>
  `).join('');

  const preservedRows = data.preserved.length > 0 ? `
    <tr class="preview-divider">
      <td colspan="3">── 以下文件不会改名（特典/Bonus，原样搬运）──</td>
    </tr>
    ${data.preserved.map(f => `
      <tr class="preview-row preview-preserved">
        <td class="preview-old">${escapeHtml(f.old_name)}</td>
        <td class="preview-arrow"></td>
        <td class="preview-new preview-preserved-label">原样保留</td>
      </tr>
    `).join('')}
  ` : '';

  return `
    <div class="preview-header">
      改名预览 — ${data.renamed.length} 个文件将重命名
      ${data.preserved.length > 0 ? `，${data.preserved.length} 个特典文件保留` : ''}
    </div>
    <table class="preview-table">
      <thead>
        <tr>
          <th>旧文件名</th>
          <th></th>
          <th>新文件名</th>
        </tr>
      </thead>
      <tbody>
        ${renamedRows}
        ${preservedRows}
      </tbody>
    </table>
  `;
}
```

---

## Step 3: CSS — rename preview styles

**File:** `/workspaces/anime_triage/frontend/css/style.css`

Add at the end of the file:

```css
/* ── Expand Preview Button ────────────────────────────── */
.btn-expand-preview {
  width: 100%;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  padding: 6px 12px;
  cursor: pointer;
  margin-bottom: 12px;
  transition: background 0.2s, color 0.2s;
  text-align: center;
}
.btn-expand-preview:hover {
  background: rgba(255,255,255,0.06);
  color: var(--text-primary);
}

/* ── Rename Preview Panel ─────────────────────────────── */
.rename-preview-panel {
  border-top: 1px solid rgba(255,255,255,0.08);
  padding-top: 14px;
  margin-bottom: 14px;
  animation: fadeIn 0.2s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.preview-header {
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin-bottom: 10px;
  font-weight: 500;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.75rem;
  font-family: var(--font-mono);
}
.preview-table th {
  color: var(--text-secondary);
  text-align: left;
  padding: 4px 6px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  font-weight: 400;
}
.preview-row td {
  padding: 4px 6px;
  vertical-align: middle;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
}
.preview-old {
  color: rgba(255,255,255,0.45);  /* dimmed old name */
}
.preview-arrow {
  color: var(--accent-primary);
  padding: 0 8px;
  font-size: 0.9rem;
  width: 20px;
}
.preview-new {
  color: #10b981;  /* green = new name */
  font-weight: 500;
}
/* Subtitle files (non-video) are slightly dimmer */
.preview-sub .preview-new {
  color: #6ee7b7;
}
/* Preserved/Bonus files — full row dimmed */
.preview-preserved td {
  color: rgba(255,255,255,0.25);
  font-style: italic;
}
.preview-preserved-label {
  color: rgba(255,255,255,0.2) !important;
}
.preview-divider td {
  color: rgba(255,255,255,0.2);
  font-size: 0.7rem;
  padding: 10px 6px 6px;
  font-style: italic;
}
.preview-loading {
  color: var(--text-secondary);
  font-size: 0.8rem;
  padding: 12px 0;
  text-align: center;
}
.preview-error {
  color: #ef4444;
  font-size: 0.8rem;
  padding: 8px;
}
```

---

## Step 4: Merge hint integration

The merge hint badge (from GEMINI_FIX_PLAN.md FEATURE 6) should appear **inside the
preview panel** as well, since when expanded, the user can see exactly which episodes
are covered here and which are in the sibling job.

In `renderPreviewPanel()`, if the parent `item` has a `merge_suggestion`, add a banner
at the top of the preview:

To pass this info through, the `/api/pending/{id}/preview` response should include
the `merge_suggestion` field from the parent job. Add to the endpoint response:

```python
# In the preview endpoint, find and include merge info
# NOTE: merge_suggestion is computed in get_queue(), not stored in the job.
# For simplicity, pass it as a query param or just let the frontend use
# the already-fetched item.merge_suggestion from the pending list.
```

In `renderPreviewPanel()`, accept a second argument `mergeSuggestion`:

```javascript
function renderPreviewPanel(data, mergeSuggestion) {
  const mergeBanner = mergeSuggestion ? `
    <div class="preview-merge-banner">
      🔗 本批次包含 E${String(Math.min(...data.renamed.map(r=>r.episode))).padStart(2,'0')}
      –E${String(Math.max(...data.renamed.map(r=>r.episode))).padStart(2,'0')}
      ，另一批次
      <code>${escapeHtml(mergeSuggestion.merge_with_filename)}</code>
      包含互补集数，确认后将合并至同一目录
    </div>
  ` : '';
  
  // ... rest of the function, put mergeBanner after preview-header
}
```

And update the call in `togglePreview()`:

```javascript
// Pass the item's merge_suggestion when rendering
const item = pendingData.find(p => p.id === jobId);  // pendingData must be stored globally
panel.innerHTML = renderPreviewPanel(data, item?.merge_suggestion);
```

This means `pendingData` (the full list from `/api/pending`) needs to be stored in a
module-level variable so `togglePreview` can access it. Check if `app.js` already does
this — look for where the pending list is stored after fetching. If not, add:

```javascript
let pendingData = [];  // store globally

// In renderPending() or wherever API data is received:
pendingData = data;   // save before rendering
```

Add CSS for the merge banner inside the preview panel:

```css
.preview-merge-banner {
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 0.78rem;
  color: #a5b4fc;
  line-height: 1.5;
}
.preview-merge-banner code {
  color: #c7d2fe;
  font-size: 0.72rem;
}
```

---

## Verification

After implementing:

1. `python reset_env.py && curl -X POST http://localhost:8765/api/scan`
2. Open http://localhost:8765/ in browser
3. Find the **赛马娘 芦毛灰姑娘 (2025)** card
4. Click **展开预览 ▾**

Confirm:
- [ ] Panel expands with a fade-in animation
- [ ] Each video file shows: `旧文件名 → 赛马娘 芦毛灰姑娘 S01E01.mkv` (green)
- [ ] Button changes to `收起预览 ▴`
- [ ] Clicking again collapses without re-fetching (uses `dataset.loaded`)
- [ ] If the job has `merge_suggestion`, the merge banner appears at the top of the panel
- [ ] Bonus/extra files appear in the bottom section, dimmed/grey, labelled `原样保留`
- [ ] `.ass`/subtitle rows appear slightly lighter green than `.mkv` rows

Test with Horimiya (which has a large Bonus/ subdirectory) to verify the
"原样保留" section appears correctly with all the Web Preview / NCED / NCOP files listed.
