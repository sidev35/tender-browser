// One tender card, and what clicking it does.
import { showToast } from './alerts.js';
import { DUE_SOON_DAYS, daysUntil, escapeHtml, fmtDue, shortCategory, shortSource } from './util.js';

// Every card shows the same set of fields (category, title, source, value,
// tracked-since, due date), so cards look the same whichever portal a tender
// came from; a missing value says so explicitly.
export function renderCard(t, isNew) {
  const d = daysUntil(t.dueDate);
  const urgency = d !== null && d < 0 ? '' : d !== null && d <= DUE_SOON_DAYS ? 'urgent' : d !== null && d <= 14 ? 'soon' : '';
  const isDirect = t.linkType === 'direct';
  const card = document.createElement('div');
  card.className = `card ${urgency} ${isNew ? 'isnew' : ''}`.trim();
  card.innerHTML = `
    <div>
      <div class="card-top-row">
        <span class="cat-badge">${escapeHtml(shortCategory(t.category))}</span>
      </div>
      <div class="card-desc" title="${escapeHtml(t.desc)}">${escapeHtml(t.desc)}</div>
      <div class="card-meta">
        <span>🏛 ${escapeHtml(shortSource(t.source))}</span>
        <span>💰 ${t.value ? escapeHtml(t.value) : 'Value not disclosed'}</span>
        ${t.firstSeen ? `<span>🕒 Tracked since ${fmtDue(t.firstSeen)}</span>` : ''}
      </div>
    </div>
    <div class="card-due">
      <div class="due-badge ${urgency}">${fmtDue(t.dueDate)}</div>
      ${d !== null ? `<div class="due-days">${d < 0 ? 'Closed' : d === 0 ? 'Due today' : d + ' day' + (d === 1 ? '' : 's') + ' left'}</div>` : ''}
    </div>
    ${t.url ? `
    <div class="card-action">
      <button class="card-action-btn" type="button" title="${isDirect ? 'Opens this tender on the source site' : t.searchText ? `Copies “${escapeHtml(t.searchText)}”, then opens the portal to search it` : 'Copies the title, then opens the portal to search it'}">${isDirect ? 'View tender ↗' : t.searchText ? 'Copy search & open portal ↗' : 'Copy title & open portal ↗'}</button>
    </div>` : ''}
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
  const lookFor = t.searchText ? ` Then look for: <em>${escapeHtml(t.desc.slice(0, 90))}${t.desc.length > 90 ? '…' : ''}</em>` : '';
  showToast(copied
    ? { title: t.searchText ? `“${escapeHtml(t.searchText)}” copied` : 'Title copied', body: how + lookFor }
    : { title: 'Couldn’t copy', body: `Search ${site} for: ${escapeHtml(text)}.${lookFor}`, kind: 'error' });
}
