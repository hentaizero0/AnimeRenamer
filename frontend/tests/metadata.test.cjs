const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../js/app.js'), 'utf8');
const context = {
  document: { addEventListener() {}, getElementById: () => ({ addEventListener() {} }) },
  window: {},
  console,
};
vm.createContext(context);
vm.runInContext(source, context);

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
console.log('metadata UI check passed');
