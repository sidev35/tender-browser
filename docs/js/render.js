// Drawing the whole page from the current state: stat tiles, the "new since
// last visit" banner, the pills (All, New, categories), and the tender cards
// grouped by category.
import { getSeen } from './alerts.js';
import { renderCard } from './cards.js';
import { DUE_SOON_DAYS, countTo, daysUntil, escapeHtml, isNew, parseValueINR, portalHome, shortSource } from './util.js';

// Cards beyond the first screenful fade up as they scroll into view (only when
// the list was just changed). Without IntersectionObserver they simply show.
const reveal = 'IntersectionObserver' in window
  ? new IntersectionObserver((entries) => entries.forEach(en => {
      if (en.isIntersecting) { en.target.classList.add('in'); reveal.unobserve(en.target); }
    }), { rootMargin: '0px 0px -8% 0px' })
  : null;

// The "New" pill: not a real category, but the tenders you haven't seen yet
// (the same ones the "New since last visit" tile counts and that carry a NEW
// badge). "Mark all as read" empties it.
export const NEW_FILTER = '__new__';

// What the category pill and the search box leave, before the value pills.
function baseTenders(state, seen) {
  let items = state.data.slice();
  if (state.category === NEW_FILTER) items = items.filter(t => isNew(t, seen));
  else if (state.category !== 'All') items = items.filter(t => t.category === state.category);
  if (state.query.trim()) {
    const q = state.query.toLowerCase();
    items = items.filter(t =>
      (t.desc || '').toLowerCase().includes(q) ||
      (t.source || '').toLowerCase().includes(q)
    );
  }
  return items;
}

// The value sorts also show a minimum-value slider (see main.js).
const isValueSort = state => state.sort === 'value_desc' || state.sort === 'value_asc';

// Applies the category pill, the search box, the minimum value and the sort order.
function visibleTenders(state, seen) {
  // The slider only applies while sorting by value. Above "Any", a tender with
  // no disclosed value is hidden: it isn't known to reach the minimum.
  const items = baseTenders(state, seen).filter(t => {
    if (!isValueSort(state) || !state.minValue) return true;
    const v = parseValueINR(t.value);
    return v !== null && v >= state.minValue;
  });
  // Value sorts put tenders with no disclosed value last, whichever way it goes.
  const val = t => parseValueINR(t.value);
  items.sort((a, b) => {
    if (state.sort === 'recent') return (b.firstSeen || '').localeCompare(a.firstSeen || '');
    if (state.sort === 'value_desc' || state.sort === 'value_asc') {
      const va = val(a), vb = val(b);
      if (va === null || vb === null) return (va === null) - (vb === null);
      return state.sort === 'value_desc' ? vb - va : va - vb;
    }
    const da = a.dueDate ? new Date(a.dueDate) : new Date('2999-01-01');
    const db = b.dueDate ? new Date(b.dueDate) : new Date('2999-01-01');
    return da - db;
  });
  return items;
}

// Stats are computed on the full data set, not just the filtered view.
function renderStats(state, seen) {
  countTo(document.getElementById('statTotal'), state.data.length);
  countTo(document.getElementById('statUrgent'), state.data.filter(t => {
    const d = daysUntil(t.dueDate); return d !== null && d <= DUE_SOON_DAYS && d >= 0;
  }).length);
  // By site, as cards show it: both TenderDetail sources count once.
  const portals = [...new Set(state.data.map(t => shortSource(t.source)))].sort();
  const sourcesEl = document.getElementById('statSources');
  countTo(sourcesEl, portals.length);
  // Hovering (or focusing) the tile lists the portals in a small panel; each
  // name opens that portal's official home page in a new tab.
  document.getElementById('statSourcesTip').innerHTML = portals.length
    ? portals.map(p => {
        const home = portalHome(p);
        return home
          ? `<a href="${escapeHtml(home)}" target="_blank" rel="noopener noreferrer" title="Open ${escapeHtml(home)}">${escapeHtml(p)} ↗</a>`
          : `<span>${escapeHtml(p)}</span>`;
      }).join('')
    : '<span>No portals yet</span>';
  const newCount = state.data.filter(t => isNew(t, seen)).length;
  countTo(document.getElementById('statNew'), newCount);

  const banner = document.getElementById('newBanner');
  if (newCount > 0) {
    document.getElementById('newBannerText').textContent =
      `${newCount} new tender${newCount > 1 ? 's' : ''} matched since your last visit.`;
    banner.classList.add('show');
  } else {
    banner.classList.remove('show');
  }
}

// Pills: New, then one per category present in the data. (No "All" pill —
// the "Matched tenders" stat tile doubles as the reset-to-all control.)
function renderPills(state, seen, onPick) {
  const newCount = state.data.filter(t => isNew(t, seen)).length;
  const pills = [
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

// The value row (label and minimum-value slider) shows only while sorting by value.
function renderValueRow(state) {
  document.getElementById('valueRow').hidden = !isValueSort(state);
}

function renderEmpty(state, groupsEl) {
  if (state.category === NEW_FILTER && !state.query.trim()) {
    groupsEl.innerHTML = '<div class="empty"><div class="radar"></div><p>No new tenders since your last visit. When the scraper finds new ones, they show up here with a NEW badge.</p></div>';
    return;
  }
  groupsEl.innerHTML = state.data.length === 0
    ? (state.lastFetchFailed
        ? '<div class="empty"><div class="radar"></div><p>Couldn\'t load live tender data — check your connection and try the refresh icon above.</p></div>'
        : '<div class="empty"><div class="radar"></div><p>No EV charging tenders currently match your categories. The scraper checks every 3 hours — check back later, or click refresh to check now.</p></div>')
    : '<div class="empty"><div class="radar"></div><p>No tenders match this filter right now. Try clearing the search, picking a different category, or changing the value filter.</p></div>';
}

// animate: let the cards rise in (a list change, not typing). onPickCategory(category) is called when a pill is clicked; onMarkRead() when
// "Mark all as read" is.
export function render(fullState, { onPickCategory, onMarkRead, animate = false }) {
  // Tiles, pills and cards all show the chosen country only (old records have no country: India).
  const state = { ...fullState, data: fullState.data.filter(t => (t.country || 'India') === fullState.country) };
  const seen = getSeen();
  const items = visibleTenders(state, seen);
  renderStats(state, seen);
  renderPills(state, seen, onPickCategory);
  renderValueRow(state);

  const groupsEl = document.getElementById('groups');
  groupsEl.innerHTML = '';
  // Cards rise in only when the list was just changed (not on every keystroke).
  groupsEl.classList.toggle('enter', animate);
  let cardNo = 0;
  if (items.length === 0) {
    renderEmpty(state, groupsEl);
    return;
  }

  if (state.category === NEW_FILTER) {
    const bar = document.createElement('div');
    bar.className = 'new-toolbar';
    bar.innerHTML = `<span>${items.length} unread tender${items.length > 1 ? 's' : ''}</span><button type="button">✓ Mark all as read</button>`;
    bar.querySelector('button').onclick = onMarkRead;
    groupsEl.appendChild(bar);
  }

  const byCat = {};
  items.forEach(t => { (byCat[t.category] = byCat[t.category] || []).push(t); });
  Object.keys(byCat).forEach(cat => {
    const groupEl = document.createElement('div');
    groupEl.className = 'group';
    groupEl.innerHTML = `<div class="group-head"><h2>${escapeHtml(cat)}</h2><span class="count">${byCat[cat].length} tender${byCat[cat].length > 1 ? 's' : ''}</span></div>`;
    const grid = document.createElement('div');
    grid.className = 'card-grid';
    byCat[cat].forEach(t => {
      const card = renderCard(t, isNew(t, seen));
      card.style.setProperty('--i', Math.min(cardNo, 12)); // stagger the first dozen
      if (animate && reveal && cardNo >= 12) { card.classList.add('reveal'); reveal.observe(card); }
      cardNo++;
      grid.appendChild(card);
    });
    groupEl.appendChild(grid);
    groupsEl.appendChild(groupEl);
  });

  document.getElementById('syncTime').textContent = new Date().toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}
