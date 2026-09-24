// Entry point: holds the page state, loads data, and wires up the controls.
// Loaded by index.html as <script type="module">.
import { checkForAlerts, hasSeenBaseline, setSeen, setupNotifyButton, showToast } from './alerts.js';
import { fetchLiveData } from './data.js';
import { NEW_FILTER, render } from './render.js';

const AUTO_REFRESH_MS = 10 * 60 * 1000; // re-check for updates every 10 min while the tab is open

// No bundled example data — the dashboard is driven entirely by the live
// data/tenders.json fetch. If that fetch fails, we show an honest empty
// state rather than stale placeholder tenders pretending to be current.
const state = {
  data: [],
  category: 'All',
  query: '',
  sort: 'due',
  lastFetchFailed: false,
};
let isRefreshing = false;

function redraw() {
  render(state, { onPickCategory: (c) => { state.category = c; redraw(); } });
}

async function refreshData({ manual = false } = {}) {
  if (isRefreshing) return;
  isRefreshing = true;
  const btn = document.getElementById('updateBtn');
  if (manual) btn.classList.add('spinning');
  try {
    const data = await fetchLiveData();
    // An empty array is a real, valid result (currently zero matches) —
    // it must still replace stale data, not be treated as "no update".
    state.lastFetchFailed = false;
    checkForAlerts(data);
    state.data = data;
    redraw();
    if (manual) showToast({ title: 'Synced', body: `Loaded ${data.length} tender(s) from the latest data sync.`, kind: 'new' });
  } catch (e) {
    state.lastFetchFailed = true;
    redraw();
    console.warn('Could not load live data/tenders.json.', e);
    if (manual) showToast({ title: 'Refresh failed', body: 'Could not reach data/tenders.json — ' + e.message, kind: 'error' });
  } finally {
    isRefreshing = false;
    if (manual) btn.classList.remove('spinning');
  }
}

// --- Controls -----------------------------------------------------------

document.getElementById('searchBox').addEventListener('input', e => { state.query = e.target.value; redraw(); });
document.getElementById('sortSel').addEventListener('change', e => { state.sort = e.target.value; redraw(); });
document.getElementById('dismissNew').addEventListener('click', () => {
  setSeen(state.data.map(t => t.id));
  redraw();
});
document.getElementById('updateBtn').addEventListener('click', () => { refreshData({ manual: true }); });

// The "New since last visit" tile opens the New pill: the tenders it counts.
const newTile = document.getElementById('statNewTile');
const showNew = () => { state.category = NEW_FILTER; redraw(); };
newTile.addEventListener('click', showNew);
newTile.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showNew(); } });

// Theme: light by default (set on <html> in index.html, and restored from
// localStorage there before the page draws); the toggle remembers the choice.
document.getElementById('themeToggle').addEventListener('click', () => {
  const root = document.documentElement;
  const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  root.setAttribute('data-theme', next);
  try { localStorage.setItem('tenderRadar_theme', next); } catch (e) {}
});

setupNotifyButton();

// --- Startup --------------------------------------------------------------

(async () => {
  // First load: pull live data, seed the "seen"/known-id baselines so
  // "NEW" badges and popups only fire for genuinely new data afterwards.
  await refreshData({ manual: false });
  if (!hasSeenBaseline()) {
    setSeen(state.data.map(t => t.id));
  }
  redraw();
})();

// Keep checking in the background: on an interval, and whenever the tab
// regains focus (covers the common case of leaving it open in a background tab).
setInterval(() => refreshData({ manual: false }), AUTO_REFRESH_MS);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') refreshData({ manual: false });
});
