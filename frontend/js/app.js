// ─── AnimeRenamer v2 — Frontend SPA ──────────────────────────────────────────

// ── State// ─────────────────────────────────────────────────────────────────────
let currentView = 'dashboard';
let pendingItems = [];
let logFilter = 'all';
let editModal = null;

// ── Helpers// ───────────────────────────────────────────────────────────────────

function timeAgo(isoString) {
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function confidenceColor(score) {
  if (score >= 0.85) return 'var(--success)';
  if (score >= 0.60) return 'var(--warning)';
  return 'var(--error)';
}

function confidenceLabel(score) {
  if (score >= 0.85) return 'high';
  if (score >= 0.60) return 'medium';
  return 'low';
}

function padNum(n) { return String(n).padStart(2, '0'); }

function modeBadge(mode) {
  return `<span class="badge badge-${mode === 'auto' ? 'blue' : 'amber'}">${mode}</span>`;
}

function statusBadge(status) {
  const map = { done: 'green', error: 'red', pending: 'amber', skipped: 'gray' };
  const icons = { done: '✓', error: '✕', pending: '⋯', skipped: '⏭' };
  return `<span class="badge badge-${map[status] || 'gray'}">${icons[status] || ''} ${status}</span>`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
  toast.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ'}</span><span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ── Navigation// ────────────────────────────────────────────────────────────────
function navigate(view) {
  currentView = view;
  const titles = { dashboard: '仪表盘', series: '番剧库', logs: '操作日志', rules: '规则目录', ignored: '已忽略目录', settings: '设置' };
  const topbarTitle = document.getElementById('topbar-title');
  if (topbarTitle && titles[view]) topbarTitle.textContent = titles[view];
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === view);
  });
  document.querySelectorAll('.view').forEach(el => {
    el.classList.toggle('active', el.id === `view-${view}`);
  });
  renderView(view);
}

// ── Main render dispatcher ─────────────────────────────────────────────────────
async function renderView(view) {
  if (view === 'dashboard') await renderDashboard();
  else if (view === 'series') await renderSeries();
  else if (view === 'logs') await renderLogs();
  else if (view === 'rules') await renderRules();
  else if (view === 'ignored') await renderIgnored();
  else if (view === 'settings') await renderSettings();
}

// ── Dashboard view ────────────────────────────────────────────────────────────
async function renderDashboard() {
  const [stats, pending, recent, dirs, autoDirs] = await Promise.all([
    API.getStats(),
    API.getPending(),
    API.getRecent(),
    API.getDirectories(),
    API.getAutoSubscriptions()
  ]);
  pendingItems = pending;

  // Stats bar
  document.getElementById('stat-pending').textContent = stats.pending;
  document.getElementById('stat-processed').textContent = stats.processed_today;
  document.getElementById('stat-errors').textContent = stats.errors;

  // Split pending into confirm and auto (for logging/hiding)
  const pendingConfirm = pending.filter(p => p.mode !== 'auto');
  // Pending auto items are actively processing, we don't display them as interactive cards

  // Pending confirm queue
  const pendingEl = document.getElementById('pending-cards');
  if (pendingConfirm.length === 0) {
    pendingEl.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✅</div>
        <p>暂无需要手动确认的队列</p>
      </div>`;
  } else {
    pendingEl.innerHTML = pendingConfirm.map(item => renderPendingCard(item)).join('');
    attachCardListeners(pendingEl);
  }

  // Auto subscriptions
  const autoEl = document.getElementById('auto-list');
  if (autoDirs.length === 0) {
    autoEl.innerHTML = `
      <div class="empty-state">
        <p style="font-size: 13px; color: var(--text-muted);">暂无开启 AUTO 模式的订阅</p>
      </div>`;
  } else {
    autoEl.innerHTML = autoDirs.map(d => `
      <div class="auto-sub-card">
        <div class="auto-sub-header">
          <span class="auto-sub-title">📺 ${escapeHtml(d.name)}</span>
          <span class="badge auto">AUTO</span>
        </div>
        <div class="auto-sub-path">📂 /${escapeHtml(d.path)}</div>
      </div>
    `).join('');
  }

  // Recent activity
  const recentEl = document.getElementById('recent-list');
  recentEl.innerHTML = recent.map(item => `
    <div class="activity-row" data-id="${item.id}">
      <div class="activity-status">${statusBadge(item.status)}</div>
      <div class="activity-info">
        <span class="activity-filename mono">${escapeHtml(item.filename)}</span>
        <span class="activity-arrow">→</span>
        <span class="activity-title">${escapeHtml(item.title)}</span>
        ${item.error_msg ? `<span class="activity-error">${escapeHtml(item.error_msg)}</span>` : ''}
      </div>
      <div class="activity-meta">
        ${modeBadge(item.mode)}
        <span class="confidence-mini" style="color:${confidenceColor(item.confidence)}">${Math.round(item.confidence * 100)}%</span>
        <span class="activity-time">${timeAgo(item.timestamp)}</span>
      </div>
    </div>
  `).join('');
}

function renderPendingCard(item) {
  const pct = Math.round(item.confidence * 100);
  const color = confidenceColor(item.confidence);
  const clsLabel = confidenceLabel(item.confidence);
  const activeConflicts = item.duplicates ? Object.keys(item.duplicates).filter(ep => {
    const activeFiles = item.duplicates[ep].filter(f => !f.ignored);
    return activeFiles.length >= 2;
  }) : [];
  return `
    <div class="pending-card" data-id="${item.id}" onclick="handleCardClick(event, '${item.id}')">
      <div class="card-header">
        <div class="card-badges">
          ${modeBadge(item.mode)}
          <span class="badge badge-gray">S${padNum(item.season)} E${padNum(item.episode)}</span>
        </div>
        <span class="card-size">${escapeHtml(item.source_size)}</span>
      </div>

      <div class="card-original">
        <span class="label">原始文件</span>
        <code class="mono filename">${escapeHtml(item.original_filename)}</code>
      </div>

      <div class="card-detected">
        <div class="detected-title-container">
          ${item.original_parsed_title && item.original_parsed_title !== item.detected_title 
            ? `<div class="detected-title-translated">
                 <div class="romaji-title">罗马音：${escapeHtml(item.original_parsed_title)}</div>
                 <div class="detected-title blinking-cn">中文：${escapeHtml(item.detected_title)}</div>
               </div>`
            : `<span class="detected-title">${escapeHtml(item.detected_title)}</span>`
          }
        </div>
      </div>
      
      <div class="tags-container" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
        <span class="episode-tag">第 ${item.season} 季</span>
        <span class="episode-tag">共 ${item.video_count} 集</span>
        ${item.has_subs ? '<span class="episode-tag" style="background:rgba(234,179,8,0.15);color:#facc15;">外挂字幕</span>' : ''}
      </div>
      
      ${activeConflicts.length > 0
        ? `<div class="merge-hint" style="background:rgba(239,68,68,0.1);border-color:rgba(239,68,68,0.2);color:#fca5a5;">
             <span class="merge-icon">⚠️</span>
             <span>发现冲突多版本: 第 ${activeConflicts.join(', ')} 集</span>
             <button class="btn btn-ghost" style="padding:2px 8px;font-size:12px;margin-left:auto;color:#fca5a5;border:1px solid rgba(239,68,68,0.3);" onclick="event.stopPropagation(); window.openConflictModal('${item.id}')">解决冲突</button>
           </div>`
        : ''
      }
      
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

      <div class="confidence-row">
        <span class="confidence-label conf-${clsLabel}">${pct}%</span>
        <div class="confidence-bar-track">
          <div class="confidence-bar-fill" style="width:${pct}%;background:${color}"></div>
        </div>
        <span class="confidence-text conf-${clsLabel}">${clsLabel}</span>
      </div>

      <div class="card-target">
        <span class="label">目标路径</span>
        <code class="mono target-path">${escapeHtml(item.target_path)}</code>
      </div>

      <div class="card-detected-time">
        <span class="label">检测时间</span>
        <span>${timeAgo(item.detected_at)}</span>
      </div>

      <div class="card-actions">
        <button class="btn btn-success btn-confirm" data-id="${item.id}" title="${activeConflicts.length > 0 ? '请先解决冲突' : '确认分类并移动'}" ${activeConflicts.length > 0 ? 'disabled' : ''}>
          ✅ 确认
        </button>
        <button class="btn btn-secondary btn-edit" data-id="${item.id}" title="Edit metadata">
          ✏️ 编辑
        </button>
        <button class="btn btn-ghost btn-skip" data-id="${item.id}" title="Skip this item">
          ⏭ 跳过
        </button>
      </div>
    </div>`;
}

function handleCardClick(event, jobId) {
  // Ignore clicks on buttons
  if (event.target.closest('button')) return;
  
  // Ignore if user is selecting text
  const selection = window.getSelection();
  if (selection && selection.toString().length > 0) {
    return;
  }
  
  openPreviewModal(jobId);
}

async function openPreviewModal(jobId) {
  const overlay = document.getElementById('preview-modal-overlay');
  const modal = document.getElementById('preview-modal');
  const body = document.getElementById('preview-modal-body');
  
  overlay.classList.add('active');
  modal.classList.add('active');
  
  body.innerHTML = '<div class="preview-loading">加载中...</div>';
  
  try {
    const resp = await fetch(`${API_BASE}/pending/${jobId}/preview`);
    if (!resp.ok) throw new Error('Failed to load preview');
    const data = await resp.json();
    const item = pendingItems.find(p => p.id === jobId);
    body.innerHTML = renderPreviewPanel(data, item?.merge_suggestion);
  } catch (e) {
    body.innerHTML = `<div class="preview-error">预览加载失败: ${e.message}</div>`;
  }
}

function closePreviewModal() {
  document.getElementById('preview-modal-overlay').classList.remove('active');
  document.getElementById('preview-modal').classList.remove('active');
}

document.getElementById('preview-modal-close')?.addEventListener('click', closePreviewModal);
document.getElementById('preview-modal-overlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) closePreviewModal();
});

window.closeConflictModal = function() {
  document.getElementById('conflict-modal-overlay').classList.remove('active');
  document.getElementById('conflict-modal').classList.remove('active');
  renderDashboard();
};

document.getElementById('conflict-modal-close')?.addEventListener('click', window.closeConflictModal);
document.getElementById('conflict-modal-overlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) window.closeConflictModal();
});

window.toggleIgnore = async function(jobId, index) {
  try {
    const btn = event.currentTarget;
    btn.disabled = true;
    await _post(`/pending/${jobId}/items/${index}/toggle_ignore`);
    
    // Refresh the dashboard immediately so the card updates in the background
    await renderDashboard();
    
    // Refresh the modal content by reopening it
    window.openConflictModal(jobId);
  } catch (e) {
    console.error(e);
    alert("Toggle failed!");
  }
};

window.openConflictModal = function(jobId) {
  const item = pendingItems.find(p => p.id === jobId);
  if (!item || !item.duplicates) return;
  
  const body = document.getElementById('conflict-modal-body');
  let html = '';
  
  for (const [ep, files] of Object.entries(item.duplicates)) {
    html += `<div style="background:rgba(255,255,255,0.02); padding: 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);">`;
    html += `<h3 style="margin-top:0;margin-bottom:8px;font-size:14px;color:#cbd5e1;">第 ${ep} 集 的多个版本</h3>`;
    html += `<div style="display:flex; flex-direction:column; gap:6px;">`;
    
    for (const f of files) {
      const isIgnored = f.ignored;
      html += `
        <div style="display:flex; align-items:center; gap:8px;">
          <input type="checkbox" id="chk-${f.index}" ${!isIgnored ? 'checked' : ''} onchange="window.toggleIgnore('${jobId}', ${f.index})" style="cursor:pointer;" />
          <label for="chk-${f.index}" style="font-family:monospace; font-size:13px; cursor:pointer; color: ${isIgnored ? '#64748b' : '#f8fafc'}; text-decoration: ${isIgnored ? 'line-through' : 'none'}; word-break: break-all;">
            ${escapeHtml(f.name)}
          </label>
        </div>
      `;
    }
    
    html += `</div></div>`;
  }
  
  body.innerHTML = html;
  
  document.getElementById('conflict-modal-overlay').classList.add('active');
  document.getElementById('conflict-modal').classList.add('active');
};

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

  const renamedRows = data.renamed.map(f => `
    <tr class="preview-row${f.is_video ? '' : ' preview-sub'}">
      <td class="preview-old">${escapeHtml(f.old_name)}</td>
      <td class="preview-arrow">→</td>
      <td class="preview-new">
        <div>${escapeHtml(f.new_name)}</div>
        <div style="font-size: 0.65rem; color: rgba(255,255,255,0.35); margin-top: 4px; font-family: var(--font-mono); word-break: break-all; display: flex; flex-direction: column; gap: 2px;">
          <span>📂 转移至: ${f.dest_root ? `[${escapeHtml(f.dest_root)}] ${escapeHtml(f.dest_dir)}/` : escapeHtml(f.new_path)}</span>
          ${f.hardlink_path ? `<span>🔗 硬链至: ${f.hardlink_root ? `[${escapeHtml(f.hardlink_root)}] ${escapeHtml(f.hardlink_dir)}/` : escapeHtml(f.hardlink_path)}</span>` : ''}
        </div>
      </td>
    </tr>
  `).join('');

  const preservedRows = data.preserved.length > 0 ? `
    <tr class="preview-divider">
      <td colspan="3">── 以下文件不会改名（特典/Bonus，原样搬运）──</td>
    </tr>
    ${data.preserved.map(f => `
      <tr class="preview-row preview-preserved">
        <td class="preview-old">${escapeHtml(f.old_name)}</td>
        <td class="preview-arrow">→</td>
        <td class="preview-new">
          <div class="preview-preserved-label">原样保留</div>
          <div style="font-size: 0.65rem; color: rgba(255,255,255,0.25); margin-top: 4px; font-family: var(--font-mono); word-break: break-all;">📂 转移至: ${f.dest_root ? `[${escapeHtml(f.dest_root)}] ${escapeHtml(f.dest_dir)}/` : escapeHtml(f.new_path)}</div>
        </td>
      </tr>
    `).join('')}
  ` : '';

  return `
    ${mergeBanner}
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

function attachCardListeners(container) {
  container.querySelectorAll('.btn-confirm').forEach(btn => {
    btn.addEventListener('click', () => handleConfirm(btn.dataset.id));
  });
  container.querySelectorAll('.btn-edit').forEach(btn => {
    btn.addEventListener('click', () => handleEdit(btn.dataset.id));
  });
  container.querySelectorAll('.btn-skip').forEach(btn => {
    btn.addEventListener('click', () => handleSkip(btn.dataset.id));
  });
}

async function handleConfirm(id) {
  const card = document.querySelector(`.pending-card[data-id="${id}"]`);
  if (!card) return;
  card.classList.add('card-processing');
  const res = await API.confirmItem(id);
  
  if (res && res.success === false) {
    showToast('错误: ' + (res.error_msg || '移动失败，请查看日志'), 'error');
    card.classList.remove('card-processing');
    return;
  }

  card.classList.add('card-done');
  showToast('已确认重命名 ✓', 'success');
  setTimeout(() => {
    card.style.maxHeight = card.offsetHeight + 'px';
    card.style.opacity = '0';
    card.style.transform = 'translateX(40px)';
    card.style.maxHeight = '0';
    card.style.margin = '0';
    card.style.padding = '0';
    setTimeout(() => {
      card.remove();
      const remaining = document.querySelectorAll('.pending-card').length;
      const stat = document.getElementById('stat-pending');
      if (stat) stat.textContent = remaining;
      if (remaining === 0) {
        document.getElementById('pending-cards').innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">✨</div>
            <p>Queue is empty — all caught up!</p>
          </div>`;
      }
    }, 400);
  }, 100);
}

async function handleSkip(id) {
  const card = document.querySelector(`.pending-card[data-id="${id}"]`);
  if (!card) return;
  card.classList.add('card-processing');
  await API.skipItem(id);
  showToast('已跳过', 'warning');
  card.style.opacity = '0';
  card.style.transform = 'translateX(-40px)';
  setTimeout(() => {
    card.style.maxHeight = '0';
    card.style.margin = '0';
    card.style.padding = '0';
    setTimeout(() => {
      card.remove();
      const remaining = document.querySelectorAll('.pending-card').length;
      const stat = document.getElementById('stat-pending');
      if (stat) stat.textContent = remaining;
      if (remaining === 0) {
        document.getElementById('pending-cards').innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">✨</div>
            <p>Queue is empty — all caught up!</p>
          </div>`;
      }
    }, 300);
  }, 200);
}

function handleEdit(id) {
  const item = pendingItems.find(p => p.id === id);
  if (!item) return;
  openEditModal(item);
}

// ── Edit Modal// ─────────────────────────────────────────────────────────────────
function openEditModal(item) {
  const overlay = document.getElementById('modal-overlay');
  const modal = document.getElementById('edit-modal');

  document.getElementById('modal-title-display').textContent = item.detected_title;
  document.getElementById('modal-field-title').value = item.detected_title;
  document.getElementById('modal-field-season').value = item.season;
  document.getElementById('modal-field-episode').value = item.episode;
  document.getElementById('modal-field-target').value = item.target_path;
  document.getElementById('modal-item-id').value = item.id;

  overlay.classList.add('active');
  modal.classList.add('active');
  document.getElementById('modal-field-title').focus();
}

function closeEditModal() {
  document.getElementById('modal-overlay').classList.remove('active');
  document.getElementById('edit-modal').classList.remove('active');
}

async function submitEdit() {
  const id = document.getElementById('modal-item-id').value;
  const payload = {
    title: document.getElementById('modal-field-title').value,
    season: parseInt(document.getElementById('modal-field-season').value, 10),
    episode: parseInt(document.getElementById('modal-field-episode').value, 10),
    target_path: document.getElementById('modal-field-target').value,
  };
  await API.confirmItem(id, payload);
  closeEditModal();
  showToast('已保存并确认 ✓', 'success');
  const card = document.querySelector(`.pending-card[data-id="${id}"]`);
  if (card) {
    card.style.opacity = '0';
    card.style.transform = 'scale(0.96)';
    setTimeout(() => { card.remove(); updatePendingCount(); }, 300);
  }
}

function updatePendingCount() {
  const remaining = document.querySelectorAll('.pending-card').length;
  const stat = document.getElementById('stat-pending');
  if (stat) stat.textContent = remaining;
}

// ── Series view// ───────────────────────────────────────────────────────────────
async function renderSeries() {
  const series = await API.getSeries();
  const grid = document.getElementById('series-grid');
  const countEl = document.getElementById('series-count');
  if (countEl) countEl.textContent = series.length;
  grid.innerHTML = series.map(s => `
    <div class="series-card" data-id="${s.name}">
      <div class="series-card-header">
        <div class="series-icon">${s.title.charAt(0)}</div>
        <div class="series-mode-wrap">${modeBadge(s.mode)}</div>
      </div>
      <div class="series-info">
        <h3 class="series-title">${escapeHtml(s.title)}</h3>
        <p class="series-title-ja">${escapeHtml(s.title_ja)}</p>
        <div class="series-meta-row">
          <span class="series-meta-item">
            <span class="meta-icon">📁</span> ${s.season_count} 季
          </span>
          <span class="series-meta-item">
            <span class="meta-icon">🎬</span> ${s.episode_count} 话
          </span>
        </div>
        <div class="series-folder mono">${escapeHtml(s.folder)}</div>
        <div class="series-footer">
          <span class="series-status status-${s.status}">${s.status}</span>
          <span class="series-time">${timeAgo(s.last_activity)}</span>
        </div>
      </div>
      <div class="series-actions">
        <button class="btn btn-sm btn-secondary" onclick="showToast('编辑功能即将上线 🚀','info')">✏️ 编辑</button>
        <button class="btn btn-sm btn-ghost" onclick="showToast('已切换模式','warning')">⇄ 切换模式</button>
      </div>
    </div>
  `).join('');
}

// ── Logs view// ─────────────────────────────────────────────────────────────────
async function renderLogs() {
  const logs = await API.getLogs(logFilter === 'all' ? null : logFilter);

  // Update filter tabs
  document.querySelectorAll('.log-filter-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === logFilter);
  });

  const filtered = logFilter === 'all' ? logs : logs.filter(l => l.status === logFilter);
  const tbody = document.getElementById('logs-tbody');
  tbody.innerHTML = filtered.map(l => `
    <tr class="log-row log-row-${l.status}">
      <td class="log-time">${timeAgo(l.timestamp)}</td>
      <td class="log-original mono">${escapeHtml(l.original_filename)}</td>
      <td class="log-renamed">
        ${l.renamed_to
          ? `<code class="mono renamed-name">${escapeHtml(l.renamed_to)}</code>
             ${l.hardlink_path ? `<div style="font-size: 0.7em; color: var(--text-muted); margin-top: 4px; font-family: var(--font-mono);">🔗 ${escapeHtml(l.hardlink_path)}</div>` : ''}`
          : `<span class="no-rename">—</span>`}
      </td>
      <td>${statusBadge(l.status)}</td>
      <td>
        <div class="conf-cell">
          <span style="color:${confidenceColor(l.confidence)}">${Math.round(l.confidence * 100)}%</span>
          <div class="conf-bar-mini-track">
            <div class="conf-bar-mini-fill" style="width:${Math.round(l.confidence*100)}%;background:${confidenceColor(l.confidence)}"></div>
          </div>
        </div>
      </td>
      <td>${modeBadge(l.mode)}</td>
      <td class="log-note">${l.error_msg ? `<span class="error-note">${escapeHtml(l.error_msg)}</span>` : ''}</td>
    </tr>
  `).join('') || `<tr><td colspan="7" class="empty-table">没有匹配的日志记录</td></tr>`;
}


// ── Rules view// ────────────────────────────────────────────────────────────────
async function renderRules() {
  const dirs = await API.getDirectories();
  const tbody = document.getElementById('rules-tbody');
  
  if (dirs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-table">暂无目录</td></tr>';
    return;
  }
  
  tbody.innerHTML = dirs.map(d => {
    const isAuto = d.mode === 'auto';
    const configType = d.has_yaml ? '<span class="badge info">triage.yaml</span>' : (d.is_root ? '<span class="badge info">内置规则</span>' : '<span class="badge" style="background:#475569">无配置</span>');
    const modeBadge = isAuto ? '<span class="badge auto">AUTO</span>' : '<span class="badge confirm">CONFIRM</span>';
    
    return `
      <tr>
        <td>
          <div style="font-weight: 500; color: var(--text-bright); font-size: 16px;">
            ${escapeHtml(d.name)}
          </div>
          <div class="mono" style="font-size: 13px; color: var(--text-muted); margin-top: 2px;">
            /${escapeHtml(d.path)}
          </div>
        </td>
        <td>${modeBadge}</td>
        <td>${configType}</td>
        <td>
          <label style="display:inline-flex; align-items:center; cursor:pointer; gap:8px;">
            <span style="font-size:14px; font-weight:600; color:#cbd5e1;">CONFIRM</span>
            <input type="checkbox" style="cursor:pointer; width:18px; height:18px;" ${isAuto ? 'checked' : ''} onchange="window.toggleDirectoryMode('${escapeHtml(d.name)}', this.checked)" />
            <span style="font-size:14px; font-weight:600; color:#cbd5e1;">AUTO</span>
          </label>
        </td>
      </tr>
    `;
  }).join('');
}

window.toggleDirectoryMode = async function(folderName, isAuto) {
  try {
    const res = await API.updateDirectoryMode(folderName, isAuto ? 'auto' : 'confirm');
    if (!res) throw new Error('API return null');
    showToast(`目录 ${folderName} 已切换至 ${isAuto ? 'AUTO' : 'CONFIRM'} 模式`, 'success');
    await renderRules();
  } catch (e) {
    console.error('Failed to toggle directory mode', e);
    showToast('切换模式失败', 'error');
    await renderRules(); // reset toggle
  }
};

// ── Ignored view
// ──────────────────────────────────────────────────────────────
async function renderIgnored() {
  const ignored = await API.getIgnored();
  const tbody = document.getElementById('ignored-tbody');
  
  if (ignored.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-table">暂无被忽略的目录</td></tr>';
    return;
  }
  
  tbody.innerHTML = ignored.map(item => {
    const reasonText = item.reason === 'no_video' ? '无视频文件' :
                       item.reason === 'low_confidence' ? '非动漫 (置信度低)' : item.reason;
    const reasonColor = item.reason === 'no_video' ? 'gray' : 'red';
    
    return `
      <tr>
        <td class="log-time">${timeAgo(item.detected_at)}</td>
        <td class="log-file mono">${escapeHtml(item.original_filename)}</td>
        <td class="log-title">${escapeHtml(item.detected_title)}</td>
        <td><span class="badge badge-${reasonColor}">${reasonText}</span></td>
        <td class="log-conf">
          <div class="conf-indicator" style="background:${confidenceColor(item.confidence)}" title="${Math.round(item.confidence*100)}%"></div>
          ${Math.round(item.confidence * 100)}%
        </td>
        <td class="log-mode">${item.items_count} files</td>
      </tr>
    `;
  }).join('');
}

// ── API status indicator ──────────────────────────────────────────────────────
async function updateApiStatus() {
  const { apiOnline, hasKey, tmdbValid } = await API.getConnectivityStatus();
  const dot = document.getElementById('api-status-dot');
  const label = document.getElementById('api-status-label');
  if (!apiOnline) {
    dot.style.background = 'var(--warning)';
    label.textContent = 'Mock 模式';
  } else if (!hasKey) {
    dot.style.background = 'var(--warning)';
    label.textContent = 'TMDB 未配置';
  } else if (tmdbValid) {
    dot.style.background = 'var(--success)';
    label.textContent = 'API 在线';
  } else {
    dot.style.background = 'var(--error)';
    label.textContent = 'TMDB Key 无效';
  }
}

// ── Init// ───────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Nav — click + keyboard
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => navigate(el.dataset.view));
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(el.dataset.view); }
    });
  });

  // Add series button
  document.getElementById('btn-add-series').addEventListener('click', () => {
    showToast('添加番剧功能即将上线 🚀', 'info');
  });

  // Log filter buttons
  document.querySelectorAll('.log-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.log-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      logFilter = btn.dataset.filter;
      renderLogs();
    });
  });

  // Modal
  document.getElementById('modal-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeEditModal();
  });

  // Start polling for live updates
  setInterval(() => {
    renderView(currentView);
  }, 3000);

  // Initial load
  setInterval(updateApiStatus, 5000);
  updateApiStatus();
  
  document.getElementById('modal-close').addEventListener('click', closeEditModal);
  document.getElementById('modal-cancel').addEventListener('click', closeEditModal);
  document.getElementById('modal-save').addEventListener('click', submitEdit);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeEditModal(); });

  // Refresh button
  document.getElementById('btn-refresh').addEventListener('click', async () => {
    const btn = document.getElementById('btn-refresh');
    btn.classList.add('spinning');
    try {
      await _post('/scan');
    } catch (e) {
      console.warn('Scan failed:', e);
    }
    await renderView(currentView);
    btn.classList.remove('spinning');
    showToast('数据已刷新', 'info');
  });

  // Boot
  await renderDashboard();
  await updateApiStatus();

  // Fade in after load
  document.body.classList.add('loaded');
});


// ── Settings ──────────────────────────────────────────────────────────────
async function renderSettings() {
  const settings = await API.getSettings();
  const input = document.getElementById('settings-tmdb-key');
  input.value = '';
  input.placeholder = settings.has_key
    ? `已配置 ${settings.key_hint}，留空则不变`
    : '输入 TMDB API key';
}

async function saveTmdbKey() {
  const key = document.getElementById('settings-tmdb-key').value.trim();
  if (!key) {
    showToast('未修改 TMDB API key', 'success');
    return;
  }
  
  const status = document.getElementById('settings-status');
  status.textContent = '保存中…';
  
  try {
    await API.updateSettings({ tmdb_api_key: key });
    status.textContent = '✓ 已保存';
    status.style.color = 'var(--success, #4caf50)';
    setTimeout(() => { status.textContent = ''; }, 3000);
    showToast('TMDB API key 已保存', 'success');
  } catch (e) {
    status.textContent = '✗ 保存失败';
    status.style.color = 'var(--error, #f44336)';
    showToast('保存失败: ' + e.message, 'error');
  }
}
