// Small helpers shared by the other modules. No DOM access here.

// "Closing soon" window, in days: the red "Due within 7 days" stat, red
// card borders, and the closing-soon alerts all use it.
export const DUE_SOON_DAYS = 7;

// A tender can only count as "new" for this many days after the scraper
// first found it, so a fresh browser or cleared site data can't flag the
// whole list as new.
export const NEW_WINDOW_DAYS = 7;

// Scraped text is untrusted: escape it before putting it into innerHTML.
export function escapeHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// "Gujarat nProcure (keyword search)" -> "Gujarat nProcure": drops the
// trailing "(...)" note that sources.json names carry.
export function shortSource(name) {
  return (name || 'Govt Portal').replace(/\s*\([^)]*\)\s*$/, '') || name;
}

const CATEGORY_SHORT = {
  'PPP / Concession / CPO Selection': 'PPP / CPO',
  'Charger Supply & Installation': 'Charger Supply',
  'Infrastructure & Electrical Works': 'Infra & Electrical',
  'Battery, BESS & Power Electronics': 'Battery & Power',
};
export function shortCategory(cat) {
  return CATEGORY_SHORT[cat] || cat || 'Uncategorized';
}

// Days from today until a "yyyy-mm-dd" date (negative if past), or null.
export function daysUntil(dateStr) {
  if (!dateStr) return null;
  const due = new Date(dateStr + 'T00:00:00');
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.round((due - now) / 86400000);
}

// New = not marked as read yet, and first found within NEW_WINDOW_DAYS.
export function isNew(t, seen) {
  if (seen.includes(t.id)) return false;
  const age = daysUntil(t.firstSeen);
  return age === null || age >= -NEW_WINDOW_DAYS;
}

// "13:00" -> "1:00 PM"
export function fmtTime(hhmm) {
  const [h, m] = hhmm.split(':').map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

// Closed = due date passed, or due today with a closing time (India time, as
// the portals show it) that has passed. Portals stop listing a tender once its
// time is up, so showing it longer sends people to a search that finds nothing.
export function isClosed(t) {
  if (!t.dueDate) return false;
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date()).map(x => [x.type, x.value]));
  const today = `${p.year}-${p.month}-${p.day}`;
  if (t.dueDate !== today) return t.dueDate < today;
  return !!t.dueTime && t.dueTime <= `${p.hour}:${p.minute}`;
}

export function fmtDue(dateStr) {
  if (!dateStr) return 'Not specified';
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

// localStorage can be unavailable (private windows, blocked site data), so
// every read falls back to a default and every write is best-effort.
export function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) { return fallback; }
}
export function saveJSON(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
}
