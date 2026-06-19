// ─── AnimeRenamer v2 — Frontend SPA ──────────────────────────────────────────

// ── State ─────────────────────────────────────────────────────────────────────
let currentView = 'dashboard';
let pendingItems = [];
let logFilter = 'all';
let editModal = null;

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Navigation ────────────────────────────────────────────────────────────────
function navigate(view) {
  currentView = view;
  const titles = { dashboard: '仪表盘', series: '番剧库', logs: '操作日志' };
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
}

// ── Dashboard view ────────────────────────────────────────────────────────────
async function renderDashboard() {
  const [stats, pending, recent] = await Promise.all([
    API.getStats(),
    API.getPending(),
    API.getRecent(),
  ]);
  pendingItems = pending;

  // Stats bar
  document.getElementById('stat-pending').textContent = stats.pending;
  document.getElementById('stat-processed').textContent = stats.processed_today;
  document.getElementById('stat-errors').textContent = stats.errors;

  // Pending queue
  const pendingEl = document.getElementById('pending-cards');
  if (pending.length === 0) {
    pendingEl.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">✨</div>
        <p>Queue is empty — all caught up!</p>
      </div>`;
  } else {
    pendingEl.innerHTML = pending.map(item => renderPendingCard(item)).join('');
    attachCardListeners(pendingEl);
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
  return `
    <div class="pending-card" data-id="${item.id}">
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
        <span class="detected-title">${escapeHtml(item.detected_title)}</span>
        <span class="episode-tag">S${padNum(item.season)}E${padNum(item.episode)}</span>
      </div>

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
        <button class="btn btn-success btn-confirm" data-id="${item.id}" title="Confirm rename">
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
  await API.confirmItem(id);
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

// ── Edit Modal ─────────────────────────────────────────────────────────────────
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

// ── Series view ───────────────────────────────────────────────────────────────
async function renderSeries() {
  const series = await API.getSeries();
  const grid = document.getElementById('series-grid');
  const countEl = document.getElementById('series-count');
  if (countEl) countEl.textContent = series.length;
  grid.innerHTML = series.map(s => `
    <div class="series-card" data-id="${s.id}">
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

// ── Logs view ─────────────────────────────────────────────────────────────────
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
          ? `<code class="mono renamed-name">${escapeHtml(l.renamed_to)}</code>`
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

// ── API status indicator ──────────────────────────────────────────────────────
async function updateApiStatus() {
  const online = API.isOnline();
  const dot = document.getElementById('api-status-dot');
  const label = document.getElementById('api-status-label');
  if (online) {
    dot.style.background = 'var(--success)';
    label.textContent = 'API 在线';
  } else {
    dot.style.background = 'var(--warning)';
    label.textContent = 'Mock 模式';
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────
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
      logFilter = btn.dataset.filter;
      renderLogs();
    });
  });

  // Modal
  document.getElementById('modal-overlay').addEventListener('click', closeEditModal);
  document.getElementById('modal-close').addEventListener('click', closeEditModal);
  document.getElementById('modal-cancel').addEventListener('click', closeEditModal);
  document.getElementById('modal-save').addEventListener('click', submitEdit);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeEditModal(); });

  // Refresh button
  document.getElementById('btn-refresh').addEventListener('click', async () => {
    const btn = document.getElementById('btn-refresh');
    btn.classList.add('spinning');
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
