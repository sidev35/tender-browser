// Drawing the whole page from the current state: stat tiles, the "new since
// last visit" banner, the pills (All, New, categories), and the tender cards
// grouped by category.
import { getSeen } from './alerts.js';
import { renderCard } from './cards.js';
import { DUE_SOON_DAYS, daysUntil, escapeHtml } from './util.js';

// The "New" pill: not a real category, but the tenders you haven't seen yet
// (the same ones the "New since last visit" tile counts and that carry a NEW
// badge). "Mark as seen" empties it.
export const NEW_FILTER = '__new__';

// Applies the category pill, the search box and the sort order.
function visibleTenders(state, seen) {
  let items = state.data.slice();
  if (state.category === NEW_FILTER) items = items.filter(t => !seen.includes(t.id));
  else if (state.category !== 'All') items = items.filter(t => t.category === state.category);
  if (state.query.trim()) {
    const q = state.query.toLowerCase();
    items = items.filter(t =>
      (t.desc || '').toLowerCase().includes(q) ||
      (t.source || '').toLowerCase().includes(q)
    );
  }
  items.sort((a, b) => {
    if (state.sort === 'recent') return (b.firstSeen || '').localeCompare(a.firstSeen || '');
    const da = a.dueDate ? new Date(a.dueDate) : new Date('2999-01-01');
    const db = b.dueDate ? new Date(b.dueDate) : new Date('2999-01-01');
    return da - db;
  });
  return items;
}

// Stats are computed on the full data set, not just the filtered view.
function renderStats(state, seen) {
  document.getElementById('statTotal').textContent = state.data.length;
  document.getElementById('statUrgent').textContent = state.data.filter(t => {
    const d = daysUntil(t.dueDate); return d !== null && d <= DUE_SOON_DAYS && d >= 0;
  }).length;
  document.getElementById('statSources').textContent = new Set(state.data.map(t => t.source)).size;
  const newCount = state.data.filter(t => !seen.includes(t.id)).length;
  document.getElementById('statNew').textContent = newCount;

  const banner = document.getElementById('newBanner');
  if (newCount > 0 && seen.length > 0) {
    document.getElementById('newBannerText').textContent =
      `${newCount} new tender${newCount > 1 ? 's' : ''} matched since your last visit.`;
    banner.classList.add('show');
  } else {
    banner.classList.remove('show');
  }
}

// Pills: All, New, then one per category present in the data.
function renderPills(state, seen, onPick) {
  const newCount = state.data.filter(t => !seen.includes(t.id)).length;
  const pills = [
    { key: 'All', label: `All (${state.data.length})` },
    { key: NEW_FILTER, label: `New (${newCount})`, extraClass: ' pill-new' },
    ...[...new Set(state.data.map(t => t.category))].map(c => (
      { key: c, label: `${c} (${state.data.filter(t => t.category === c).length})` })),
  ];
  const wrap = document.getElementById('categoryPills');
  wrap.innerHTML = '';
  pills.forEach(({ key, label, extraClass = '' }) => {
    const el = document.createElement('div');
    el.className = 'pill' + extraClass + (state.category === key ? ' active' : '');
    el.textContent = label;
    el.onclick = () => onPick(key);
    wrap.appendChild(el);
  });
}

function renderEmpty(state, groupsEl) {
  if (state.category === NEW_FILTER && !state.query.trim()) {
    groupsEl.innerHTML = '<div class="empty">No new tenders since your last visit. When the scraper finds new ones, they show up here with a NEW badge.</div>';
    return;
  }
  groupsEl.innerHTML = state.data.length === 0
    ? (state.lastFetchFailed
        ? '<div class="empty">Couldn\'t load live tender data — check your connection and try the refresh icon above.</div>'
        : '<div class="empty">No EV charging tenders currently match your categories. The scraper checks every 3 hours — check back later, or click refresh to check now.</div>')
    : '<div class="empty">No tenders match this filter right now. Try clearing the search or picking a different category.</div>';
}

// onPickCategory(category) is called when a pill is clicked.
export function render(state, { onPickCategory }) {
  const seen = getSeen();
  const items = visibleTenders(state, seen);
  renderStats(state, seen);
  renderPills(state, seen, onPickCategory);

  const groupsEl = document.getElementById('groups');
  groupsEl.innerHTML = '';
  if (items.length === 0) {
    renderEmpty(state, groupsEl);
    return;
  }

  const byCat = {};
  items.forEach(t => { (byCat[t.category] = byCat[t.category] || []).push(t); });
  Object.keys(byCat).forEach(cat => {
    const groupEl = document.createElement('div');
    groupEl.className = 'group';
    groupEl.innerHTML = `<div class="group-head"><h2>${escapeHtml(cat)}</h2><span class="count">${byCat[cat].length} tender${byCat[cat].length > 1 ? 's' : ''}</span></div>`;
    const grid = document.createElement('div');
    grid.className = 'card-grid';
    byCat[cat].forEach(t => grid.appendChild(renderCard(t, !seen.includes(t.id))));
    groupEl.appendChild(grid);
    groupsEl.appendChild(groupEl);
  });

  document.getElementById('syncTime').textContent = new Date().toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}
