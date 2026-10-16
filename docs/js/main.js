// Entry point: holds the page state, loads data, and wires up the controls.
// Loaded by index.html as <script type="module">.
import { checkForAlerts, hasSeenBaseline, setSeen, setupNotifyButton, showToast } from './alerts.js';
import { fetchLiveData } from './data.js';
import { initEffects, switchThemeWithReveal } from './fx.js';
import { initGlobe } from './globe.js';
import { DUE_FILTER, NEW_FILTER, render } from './render.js';
import { VALUE_STOPS, fmtINR, isClosed, loadJSON, saveJSON } from './util.js';

const AUTO_REFRESH_MS = 10 * 60 * 1000; // re-check for updates every 10 min while the tab is open

// No bundled example data — the dashboard is driven entirely by the live
// data/tenders.json fetch. If that fetch fails, we show an honest empty
// state rather than stale placeholder tenders pretending to be current.
// Email links open the dashboard on a view: ?view=new (the New pill) or ?view=closing (Closing soon).
function startView() {
  try {
    const v = new URLSearchParams(window.location.search).get('view');
    if (v === 'new') return NEW_FILTER;
    if (v === 'closing') return DUE_FILTER;
  } catch (e) {}
  return 'All';
}

const state = {
  data: [],
  category: startView(),
  country: loadJSON('tenderRadar_country', 'India'),
  query: '',
  sort: 'due',
  minValue: 0, // minimum-value slider (shown with the value sorts): 0 = any value
  lastFetchFailed: false,
};
let isRefreshing = false;

function markAllRead() {
  setSeen(state.data.map(t => t.id));
  redraw();
}

// animate: the list was just changed (a pill, the country, the sort), so the cards rise in.
function redraw(animate = false) {
  render(state, {
    onPickCategory: (c) => { state.category = c; redraw(true); },
    onMarkRead: markAllRead,
    animate,
  });
}

async function refreshData({ manual = false } = {}) {
  if (isRefreshing) return;
  isRefreshing = true;
  const btn = document.getElementById('updateBtn');
  if (manual) btn.classList.add('spinning');
  try {
    // Tenders whose closing time has passed are hidden at once, without waiting
    // for the next scraper run to drop them.
    const data = (await fetchLiveData()).filter(t => !isClosed(t));
    // An empty array is a real, valid result (currently zero matches) —
    // it must still replace stale data, not be treated as "no update".
    // Nothing new: leave the page exactly as it is (no redraw, so no animation replay).
    const unchanged = !manual && !state.lastFetchFailed && JSON.stringify(data) === JSON.stringify(state.data);
    state.lastFetchFailed = false;
    checkForAlerts(data);
    if (unchanged) return;
    state.data = data;
    redraw(true);
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

// The country comes from the globe picker (js/globe.js). A country with no tender
// source just shows an empty page that says so (render.js), never another country's tenders.
function setCountry(country) {
  if (country === state.country) return;
  state.country = country;
  state.category = 'All'; // a category pill from the other country may not exist here
  saveJSON('tenderRadar_country', state.country);
  redraw(true);
}
document.getElementById('searchBox').addEventListener('input', e => { state.query = e.target.value; redraw(); });
// The minimum-value slider sits beside the "Value" label, which shows only while
// sorting by value. It moves along VALUE_STOPS; leaving the value sorts clears it.
const slider = document.getElementById('minValueSlider');
const sliderLabel = document.getElementById('minValueLabel');
slider.max = String(VALUE_STOPS.length - 1);
const showMinValue = () => { sliderLabel.textContent = state.minValue ? fmtINR(state.minValue) + '+' : 'Any value'; };
// The slider's track is filled up to the thumb (read by the CSS as --p).
const paintSlider = () => slider.style.setProperty('--p', (Number(slider.value) / Number(slider.max)) * 100 + '%');
paintSlider();
slider.addEventListener('input', () => {
  state.minValue = VALUE_STOPS[Number(slider.value)];
  showMinValue();
  paintSlider();
  redraw();
});
document.getElementById('sortSel').addEventListener('change', e => {
  state.sort = e.target.value;
  if (!state.sort.startsWith('value_')) { // the slider is hidden now: drop its filter
    state.minValue = 0;
    slider.value = '0';
    showMinValue();
  }
  paintSlider();
  redraw(true);
});
document.getElementById('dismissNew').addEventListener('click', markAllRead);
document.getElementById('updateBtn').addEventListener('click', () => { refreshData({ manual: true }); });

// The "New since last visit" tile opens the New pill: the tenders it counts.
const newTile = document.getElementById('statNewTile');
const showNew = () => { state.category = NEW_FILTER; redraw(true); };
newTile.addEventListener('click', showNew);
newTile.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showNew(); } });

// The "Due within 7 days" tile opens the Closing soon pill.
const dueTile = document.getElementById('statDueTile');
const showDue = () => { state.category = DUE_FILTER; redraw(true); };
dueTile.addEventListener('click', showDue);
dueTile.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showDue(); } });

// The "Matched tenders" tile resets the category filter back to all tenders
// (there's no "All" pill — this tile doubles as that control).
const totalTile = document.getElementById('statTotalTile');
const showAll = () => { state.category = 'All'; redraw(true); };
totalTile.addEventListener('click', showAll);
totalTile.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showAll(); } });

// Theme: light by default (set on <html> in index.html, and restored from
// localStorage there before the page draws); the toggle remembers the choice.
document.getElementById('themeToggle').addEventListener('click', (e) => {
  const root = document.documentElement;
  const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  switchThemeWithReveal(e.currentTarget, () => root.setAttribute('data-theme', next));
  try { localStorage.setItem('tenderRadar_theme', next); } catch (err) {}
});

initEffects();
initGlobe({ country: state.country, onChange: setCountry });

setupNotifyButton();

// --- Startup --------------------------------------------------------------

(async () => {
  // First load: pull live data, seed the "seen"/known-id baselines so
  // "NEW" badges and popups only fire for genuinely new data afterwards.
  await refreshData({ manual: false });
  // (Only once data actually loaded: seeding an empty list would leave every
  // tender that arrives later flagged as new.)
  if (!hasSeenBaseline() && state.data.length > 0) {
    setSeen(state.data.map(t => t.id));
  }
  redraw(true);
})();

// Keep checking in the background: on an interval, and whenever the tab
// regains focus (covers the common case of leaving it open in a background tab).
setInterval(() => refreshData({ manual: false }), AUTO_REFRESH_MS);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') refreshData({ manual: false });
});

// Back-to-top button: appears once the list has been scrolled a little.
const toTop = document.getElementById('toTop');
window.addEventListener('scroll', () => toTop.classList.toggle('show', window.scrollY > 500), { passive: true });
toTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
