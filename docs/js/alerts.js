// Everything that tells the visitor something happened: in-page toasts,
// browser (system) notifications, and remembering which tenders they've
// already been told about, so nothing alerts twice.
import { DUE_SOON_DAYS, daysUntil, escapeHtml, fmtDue, loadJSON, saveJSON } from './util.js';

// Remembered per browser in localStorage:
//   tenderRadar_seen             ids already seen (drives "NEW" badges and the banner)
//   tenderRadar_knownIds         ids present at the last check (drives "new tender" alerts)
//   tenderRadar_dueSoonNotified  id -> due date already alerted as closing soon
export const getSeen = () => loadJSON('tenderRadar_seen', []);
export const setSeen = (ids) => saveJSON('tenderRadar_seen', ids);
export const hasSeenBaseline = () => loadJSON('tenderRadar_seen', null) !== null;

// `title` and `body` are HTML: escape any scraped text before passing it in.
export function showToast({ title, body, kind = 'new' }) {
  const stack = document.getElementById('toastStack');
  const el = document.createElement('div');
  el.className = 'toast' + (kind === 'due' ? ' due' : kind === 'error' ? ' error' : '');
  el.innerHTML = `<button class="toast-close" aria-label="Dismiss">&times;</button><strong>${title}</strong><p>${body}</p>`;
  el.querySelector('.toast-close').addEventListener('click', () => el.remove());
  stack.appendChild(el);
  setTimeout(() => el.remove(), 12000);
}

function maybeNativeNotify(title, body) {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  try { new Notification(title, { body }); } catch (e) {}
}

// Compares freshly fetched data against what we've seen before to raise
// two kinds of alerts: brand-new tenders, and tenders newly inside the
// "closing soon" window. Both are deduped via localStorage so the same
// tender doesn't re-notify on every periodic check.
export function checkForAlerts(data) {
  const knownIds = loadJSON('tenderRadar_knownIds', []);
  const isFirstRun = knownIds.length === 0;
  const newOnes = isFirstRun ? [] : data.filter(t => !knownIds.includes(t.id));
  saveJSON('tenderRadar_knownIds', data.map(t => t.id));

  if (newOnes.length > 0) {
    const title = `${newOnes.length} new tender${newOnes.length > 1 ? 's' : ''} matched`;
    const body = newOnes.slice(0, 3).map(t => escapeHtml(t.desc)).join(' • ') + (newOnes.length > 3 ? ' …' : '');
    showToast({ title, body, kind: 'new' });
    maybeNativeNotify(title, body);
  }

  const dueSoonNotified = loadJSON('tenderRadar_dueSoonNotified', {});
  const dueSoon = data.filter(t => {
    const d = daysUntil(t.dueDate);
    return d !== null && d >= 0 && d <= DUE_SOON_DAYS && dueSoonNotified[t.id] !== t.dueDate;
  });
  if (dueSoon.length > 0) {
    dueSoon.forEach(t => { dueSoonNotified[t.id] = t.dueDate; });
    saveJSON('tenderRadar_dueSoonNotified', dueSoonNotified);
    if (!isFirstRun) {
      const title = `${dueSoon.length} tender${dueSoon.length > 1 ? 's' : ''} closing within ${DUE_SOON_DAYS} days`;
      const body = dueSoon.slice(0, 3).map(t => `${escapeHtml(t.desc)} (${fmtDue(t.dueDate)})`).join(' • ') + (dueSoon.length > 3 ? ' …' : '');
      showToast({ title, body, kind: 'due' });
      maybeNativeNotify(title, body);
    }
  }
}

// The bell button in the header: asks for notification permission.
export function setupNotifyButton() {
  const btn = document.getElementById('notifyToggle');
  function updateUI() {
    if (typeof Notification === 'undefined') { btn.style.display = 'none'; return; }
    if (Notification.permission === 'granted') {
      btn.classList.add('active');
      btn.title = 'Browser notifications enabled for new & closing-soon tenders';
    } else {
      btn.classList.remove('active');
      btn.title = 'Enable browser notifications for new & closing-soon tenders';
    }
  }
  btn.addEventListener('click', async () => {
    if (typeof Notification === 'undefined') return;
    let perm = Notification.permission;
    if (perm === 'default') {
      perm = await Notification.requestPermission();
    }
    if (perm === 'granted') {
      // Fires every click (not just the first grant) so the button doubles as a
      // "test my notifications" action — click it any time to confirm alerts work.
      showToast({ title: 'Notifications enabled', body: "You'll see an alert here, and as a system notification, when a new tender matches or one moves inside its closing window.", kind: 'new' });
      maybeNativeNotify('Tender Radar notifications enabled', "You'll be alerted here when a new tender matches or one is closing soon.");
    } else if (perm === 'denied') {
      showToast({ title: 'Notifications blocked', body: 'Your browser blocked or previously denied this request. Allow notifications for this site in your browser\'s site settings, then click the bell again.', kind: 'error' });
    }
    updateUI();
  });
  updateUI();
}
