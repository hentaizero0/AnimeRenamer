const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../js/app.js'), 'utf8');
const themeRadios = ['bili', 'terminal', 'swiss', 'midcentury', 'y2k'].map(value => ({ value, checked: false }));
const themeStorage = new Map();
const context = {
  document: {
    documentElement: { dataset: {} },
    addEventListener() {},
    querySelectorAll: selector => selector.includes('appearance-theme') ? themeRadios : [],
    getElementById: () => ({ addEventListener() {} }),
  },
  localStorage: {
    getItem: key => themeStorage.get(key) ?? null,
    setItem: (key, value) => themeStorage.set(key, value),
  },
  window: {},
  console,
};
vm.createContext(context);
vm.runInContext(source, context);

assert.equal(context.setTheme('terminal'), 'terminal');
assert.equal(context.document.documentElement.dataset.theme, 'terminal');
assert.equal(themeStorage.get('anime-renamer-theme'), 'terminal');
assert.deepEqual(themeRadios.filter(radio => radio.checked).map(radio => radio.value), ['terminal']);
themeStorage.set('anime-renamer-theme', 'midcentury');
assert.equal(context.restoreTheme(), 'midcentury');
assert.deepEqual(themeRadios.filter(radio => radio.checked).map(radio => radio.value), ['midcentury']);
themeStorage.set('anime-renamer-theme', 'unknown-theme');
assert.equal(context.restoreTheme(), 'bili');
assert.equal(context.document.documentElement.dataset.theme, 'bili');

const item = {
  id: 'jojo', mode: 'confirm', detected_title: 'JOJO的奇妙冒险',
  original_filename: 'JoJo', source_size: '2/2 items', target_path: '/fixture/JoJo',
  season: 6, episode: 1, video_count: 2, confidence: 1, has_subs: false,
  detected_at: new Date().toISOString(), tmdb_id: 45790, season_title: '飙马野郎篇',
};
const card = context.renderPendingCard(item);
const cardWithBackdrop = context.renderPendingCard({ ...item, backdrop_path: '/frieren-backdrop.jpg' });
const preview = context.renderPreviewPanel({
  anime_name: item.detected_title, season: 6, video_count: 2,
  tmdb_id: 45790, season_title: item.season_title, renamed: [], preserved: [],
}, null);
for (const html of [card, preview]) {
  assert.match(html, /飙马野郎篇/);
  assert.match(html, /https:\/\/www\.themoviedb\.org\/tv\/45790/);
  assert.match(html, /https:\/\/www\.themoviedb\.org\/tv\/45790\/season\/6/);
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noopener noreferrer"/);
}
assert.match(card, /第 6 季/);
assert.match(card, /共 2 集/);
assert.match(cardWithBackdrop, /class="pending-card has-backdrop"/);
assert.match(cardWithBackdrop, /https:\/\/image\.tmdb\.org\/t\/p\/w500\/frieren-backdrop\.jpg/);
assert.match(cardWithBackdrop, /loading="lazy"/);
assert.doesNotMatch(context.renderPendingCard({ ...item, season_title: 'Season 6' }), /【Season 6】/);

const unsafe = context.renderPendingCard({ ...item, backdrop_path: 'https://attacker.test/image.jpg', season_title: '<img onerror=alert(1)>', tmdb_id: '1" onclick="alert(1)' });
assert.doesNotMatch(unsafe, /<img/);
assert.doesNotMatch(unsafe, /https:\/\/www\.themoviedb\.org\/tv\/1/);
assert.match(unsafe, /TMDB 未匹配/);

const grouped = context.groupPendingItems([
  { id: 'rez-romanized', detected_title: 'Re Zero kara Hajimeru Isekai Seikatsu', tmdb_id: 65942 },
  { id: 'rez-chinese', detected_title: 'Re：从零开始的异世界生活', tmdb_id: 65942 },
  { id: 'uma-english', detected_title: 'Uma Musume Cinderella Gray', tmdb_id: 262700 },
  { id: 'uma-romanized', detected_title: 'Uma Musume Shinderera Gurei', tmdb_id: 262700 },
  { id: 'rez-no-id-romanized', detected_title: 'Re Zero kara Hajimeru Isekai Seikatsu' },
  { id: 'rez-no-id-chinese', detected_title: 'Re：从零开始的异世界生活' },
]);
assert.deepEqual(JSON.parse(JSON.stringify(grouped.map(({ title, items }) => [title, items.map(item => item.id)]))), [
  ['Re Zero kara Hajimeru Isekai Seikatsu', ['rez-romanized', 'rez-chinese']],
  ['Uma Musume Cinderella Gray', ['uma-english', 'uma-romanized']],
  ['Re Zero kara Hajimeru Isekai Seikatsu', ['rez-no-id-romanized']],
  ['Re：从零开始的异世界生活', ['rez-no-id-chinese']],
]);

const shareText = context.formatLogsForClipboard([{
  id: 'job-log-1', status: 'error', title: 'Frieren', mode: 'confirm', confidence: 0.8,
  timestamp: '2026-09-28T10:11:12+00:00', source_path: '/downloads/Frieren', dest_path: '/library/Frieren',
  file_operations: [{
    operation: 'rename', status: 'failed', source_path: '/downloads/Frieren/01.mkv',
    dest_path: '/library/Frieren/Season 01/Frieren S01E01.mkv', error_msg: 'Target already exists',
  }],
  error_msg: 'Target already exists',
}]);
assert.match(shareText, /来源目录：\/downloads\/Frieren/);
assert.match(shareText, /\/downloads\/Frieren\/01\.mkv → \/library\/Frieren\/Season 01\/Frieren S01E01\.mkv/);
assert.match(shareText, /错误：Target already exists/);
assert.doesNotMatch(shareText, /置信度/);

const lowConfidenceLog = {
  id: 'job-low-confidence', status: 'done', title: 'Low confidence', mode: 'confirm', confidence: 0.79,
  source_path: '/downloads/source', dest_path: '/library/target', file_operations: [],
};
assert.match(context.renderLogEntry(lowConfidenceLog), /置信度 79%/);
assert.match(context.formatLogsForClipboard([lowConfidenceLog]), /置信度：? 79%/);
assert.doesNotMatch(context.renderLogEntry({ ...lowConfidenceLog, confidence: 0.8 }), /置信度/);
assert.equal(context.formatLogTimestamp(null), '时间未记录');
console.log('metadata UI check passed');
