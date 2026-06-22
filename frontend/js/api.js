// ─── API Layer ────────────────────────────────────────────────────────────────
// Tries the real backend first; falls back to MOCK data on any network error.

const API_BASE = 'http://localhost:8765/api';
let _apiOnline = null; // null = untested, true/false = cached result

async function _checkOnline() {
  if (_apiOnline === true) return true;
  try {
    const r = await fetch(`${API_BASE}/stats`, { signal: AbortSignal.timeout(1500) });
    _apiOnline = r.ok;
  } catch {
    _apiOnline = false;
  }
  return _apiOnline;
}

async function _get(path) {
  const online = await _checkOnline();
  if (!online) return null;
  try {
    const r = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(3000) });
    if (!r.ok) return null;
    return r.json();
  } catch {
    _apiOnline = false;
    return null;
  }
}

async function _post(path, body) {
  const online = await _checkOnline();
  if (!online) return null;
  try {
    const r = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) return null;
    return r.json();
  } catch {
    _apiOnline = false;
    return null;
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

const API = {
  async getStats() {
    return (await _get('/stats')) ?? MOCK.stats;
  },
  async getPending() {
    return (await _get('/pending')) ?? MOCK.pending;
  },
  async getRecent() {
    return (await _get('/recent')) ?? MOCK.recent;
  },
  async getIgnored() {
    return (await _get('/ignored')) ?? [];
  },
  async getSeries() {
    return (await _get('/series')) ?? MOCK.series;
  },
  async getLogs(status = null) {
    const qs = status ? `?status=${status}` : '';
    return (await _get(`/logs${qs}`)) ?? MOCK.logs;
  },
  async confirmItem(id, payload = {}) {
    const res = await _post(`/pending/${id}/confirm`, payload);
    if (!res) {
      // Optimistic mock update
      const idx = MOCK.pending.findIndex(p => p.id === id);
      if (idx !== -1) MOCK.pending.splice(idx, 1);
      MOCK.stats.pending = Math.max(0, MOCK.stats.pending - 1);
      MOCK.stats.processed_today += 1;
    }
    return res ?? { ok: true };
  },
  async skipItem(id) {
    const res = await _post(`/pending/${id}/skip`, {});
    if (!res) {
      const idx = MOCK.pending.findIndex(p => p.id === id);
      if (idx !== -1) MOCK.pending.splice(idx, 1);
      MOCK.stats.pending = Math.max(0, MOCK.stats.pending - 1);
    }
    return res ?? { ok: true };
  },
  getDirectories: async () => {
    return (await _get('/directories')) ?? [];
  },
  getAutoSubscriptions: async () => {
    return (await _get('/auto_subscriptions')) ?? [];
  },
  updateDirectoryMode: async (folder, mode) => {
    return await _post(`/directories/${encodeURIComponent(folder)}/mode`, { mode });
  async getSettings() {
    return (await _get('/settings')) ?? { tmdb_api_key: '' };
  },
  async updateSettings(data = {}) {
    return (await _post('/settings', data)) ?? { status: 'ok' };
  },

  },
  isOnline() { return _apiOnline === true; },
};
