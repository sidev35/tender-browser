// One tender card, and what clicking it does.
import { showToast } from './alerts.js';
import { DUE_SOON_DAYS, daysUntil, displayDesc, escapeHtml, fmtDue, fmtTime, shortCategory, shortSource } from './util.js';

// Small line icons (24x24, stroked in the card's colour).
const ICONS = {
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
  plug: '<path d="M9 2v6M15 2v6M7 8h10v4a5 5 0 0 1-10 0V8zM12 17v5"/>',
  deal: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
  battery: '<rect x="2" y="7" width="17" height="10" rx="2"/><path d="M22 11v2M6 10v4M10 10v4"/>',
  traffic: '<rect x="8" y="2" width="8" height="20" rx="3"/><circle cx="12" cy="7" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="17" r="1.2"/>',
  anchor: '<circle cx="12" cy="5" r="2"/><path d="M12 7v14M8 11h8M5 12H2a10 10 0 0 0 20 0h-3"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3z"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4 2.6-2.6z"/>',
  building: '<path d="M3 21h18M5 21V8l7-4 7 4v13M9 21v-6h6v6"/>',
  pin: '<path d="M12 21s7-6.2 7-11a7 7 0 0 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const svg = (name, size = 22) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;

// Each category gets an icon and a cool-toned hue (all within the sky-blue family).
const CATEGORY_STYLE = {
  'Charger Supply & Installation': { icon: 'bolt', hue: '#38BDF8' },
  'Other EV Charging': { icon: 'plug', hue: '#60A5FA' },
  'PPP / Concession / CPO Selection': { icon: 'deal', hue: '#A78BFA' },
  'Battery, BESS & Power Electronics': { icon: 'battery', hue: '#818CF8' },
  'Traffic Management & ITS': { icon: 'traffic', hue: '#22D3EE' },
  Marine: { icon: 'anchor', hue: '#2DD4BF' },
  Defence: { icon: 'shield', hue: '#94A3B8' },
  'Infrastructure & Electrical Works': { icon: 'wrench', hue: '#7DD3FC' },
};
const DEFAULT_STYLE = { icon: 'bolt', hue: '#38BDF8' };

// Every card shows the same set of fields (category, title, source, value,
// tracked-since, due date), so cards look the same whichever portal a tender
// came from; a missing value says so explicitly.
export function renderCard(t, isNew) {
  const d = daysUntil(t.dueDate);
  const urgency = d !== null && d < 0 ? '' : d !== null && d <= DUE_SOON_DAYS ? 'urgent' : d !== null && d <= 14 ? 'soon' : '';
  const isDirect = t.linkType === 'direct';
  const style = CATEGORY_STYLE[t.category] || DEFAULT_STYLE;
  const card = document.createElement('div');
  card.className = `card ${urgency} ${isNew ? 'isnew' : ''}`.trim();
  card.style.setProperty('--cat', style.hue);
  // How much of a 30-day window is left, as a thin bar under the due date.
  const left = d === null || d < 0 ? 0 : Math.min(1, d / 30);
  card.innerHTML = `
    <div class="card-icon">${svg(style.icon)}</div>
    <div class="card-main">
      <div class="card-top-row">
        <span class="cat-badge">${escapeHtml(shortCategory(t.category))}</span>
      </div>
      <div class="card-desc" title="${escapeHtml(displayDesc(t.desc))}">${escapeHtml(displayDesc(t.desc))}</div>
      <div class="card-meta">
        <span class="chip">${svg('building', 13)}${escapeHtml(shortSource(t.source))}</span>
        ${t.location ? `<span class="chip">${svg('pin', 13)}${escapeHtml(t.location)}</span>` : ''}
        ${t.firstSeen ? `<span class="chip">${svg('clock', 13)}Tracked since ${fmtDue(t.firstSeen)}</span>` : ''}
      </div>
    </div>
    <div class="card-due">
      <div class="due-badge ${urgency}">${fmtDue(t.dueDate)}</div>
      ${d !== null ? `<div class="due-days">${d < 0 ? 'Closed' : d === 0 ? 'Due today' : d + ' day' + (d === 1 ? '' : 's') + ' left'}${t.dueTime && d >= 0 ? ' · ' + fmtTime(t.dueTime) : ''}</div>
      <div class="due-bar ${urgency}"><i style="width:${Math.round(left * 100)}%"></i></div>` : ''}
    </div>
    <div class="card-foot">
      <div class="card-value">
        <span class="cv-label">Value</span>
        ${t.value ? `<span class="cv-amt">${escapeHtml(t.value)}</span>` : '<span class="cv-amt nd">Not disclosed</span>'}
      </div>
      ${t.url ? `<button class="card-action-btn" type="button" title="${isDirect ? 'Opens this tender on the source site' : t.searchText ? `Copies “${escapeHtml(t.searchText)}”, then opens the portal to search it` : 'Copies the title, then opens the portal to search it'}">${isDirect ? 'View tender' : t.searchText ? 'Copy search &amp; open portal' : 'Copy title &amp; open portal'}<span class="arrow" aria-hidden="true">↗</span></button>` : ''}
    </div>
  `;
  if (t.url) {
    card.classList.add('clickable');
    card.addEventListener('click', () => openTender(t));
  }
  return card;
}

// One click, no popup. "direct" tenders (TenderDetail, EESL) link to the
// tender itself, so just open it. For the rest the link is the portal's
// search/listing page (the per-tender links there are session-bound), so
// copy the title first for the visitor to paste into the portal's search.
// Records saved before linkType existed default to the search behaviour,
// which still works for a direct link.
async function openTender(t) {
  if (t.linkType === 'direct') {
    window.open(t.url, '_blank', 'noopener');
    return;
  }
  // What to paste: the portal's own search keyword when the source sets one
  // (searchText, from sources.json: keyword-search portals find nothing for a
  // full title), else the title. Start the copy while this page still has
  // focus (the clipboard API refuses unfocused pages), then open the tab
  // within the same click so popup blockers allow it. Only await after both
  // have started.
  const text = t.searchText || t.desc;
  let copyDone;
  try { copyDone = navigator.clipboard.writeText(text); } catch (err) { copyDone = Promise.reject(err); }
  window.open(t.url, '_blank', 'noopener');
  let copied = false;
  try { await copyDone; copied = true; } catch (err) {}
  const site = escapeHtml(shortSource(t.source));
  const how = t.searchHint ? escapeHtml(t.searchHint) : `Paste it into the search box on ${site}, then enter the captcha if asked.`;
  // With a keyword, the portal lists a few results: say which one this is.
  const lookFor = t.searchText ? ` Then look for: <em>${escapeHtml(displayDesc(t.desc).slice(0, 90))}${t.desc.length > 90 ? '…' : ''}</em>` : '';
  showToast(copied
    ? { title: t.searchText ? `“${escapeHtml(t.searchText)}” copied` : 'Title copied', body: how + lookFor }
    : { title: 'Couldn’t copy', body: `Search ${site} for: ${escapeHtml(text)}.${lookFor}`, kind: 'error' });
}
