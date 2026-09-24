// Small helpers shared by the other modules. No DOM access here.

// "Closing soon" window, in days: the red "Due within 7 days" stat, red
// card borders, and the closing-soon alerts all use it.
export const DUE_SOON_DAYS = 7;

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
