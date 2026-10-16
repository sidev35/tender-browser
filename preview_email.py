"""
Live preview of the digest email, without sending or receiving anything.

    python preview_email.py            # then open http://localhost:8001
    python preview_email.py --port 9000 --no-open

It renders the real email (email_template.html / email_template.txt, filled in
by tender_radar/notify.py) with sample tenders taken from docs/data/tenders.json,
and shows it in the browser. Edit the template or notify.py and save: the page
reloads by itself within a second. Nothing is sent: no SMTP settings are read.

The preview page has buttons for light / dark theme, desktop / phone width, and
the plain-text version, and a switch to empty the two sections.
"""

import argparse
import importlib
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "docs", "data", "tenders.json")
WATCHED = [
    os.path.join(ROOT, "email_template.html"),
    os.path.join(ROOT, "email_template.txt"),
    os.path.join(ROOT, "tender_radar", "notify.py"),
]

SAMPLE = [
    {
        "id": "S1", "desc": "Selection of Charge Point Operator for 120 EV charging stations along national highways",
        "source": "CPPP / etenders.gov.in", "category": "PPP / Concession / CPO Selection", "location": "Maharashtra",
        "dueDate": "2026-10-24", "value": "₹14.5 Crore", "url": "https://example.com/t/1", "linkType": "direct",
    },
    {
        "id": "S2", "desc": "Supply, installation and commissioning of 60 kW DC fast chargers (CCS2) with 3-year warranty",
        "source": "Tender18", "category": "Charger Supply & Installation", "location": "Uttar Pradesh",
        "dueDate": "2026-11-02", "value": "₹2.4 Crore", "url": "https://example.com/t/2", "linkType": "direct",
    },
    {
        "id": "S3", "desc": "Battery energy storage system (BESS) 50 MWh with PCS and EMS",
        "source": "Rajasthan e-Tendering", "category": "Battery, BESS & Power Electronics", "location": "Rajasthan",
        "dueDate": "2026-11-12", "value": "₹180 Crore", "url": "https://example.com/portal", "linkType": "search",
    },
    {
        "id": "S4", "desc": "Unified ATMS and ANPR cameras for expressway incident detection",
        "source": "Buying for Victoria", "category": "Traffic Management & ITS", "location": "Victoria",
        "dueDate": "2026-11-20", "url": "https://example.com/t/4", "linkType": "direct",
    },
]


def sample_records():
    """Real tenders from the saved data when there are some, else the built-in samples."""
    try:
        with open(DATA, encoding="utf-8") as f:
            records = [t for t in json.load(f) if t.get("desc")]
    except (OSError, ValueError):
        records = []
    if len(records) < 4:
        records = SAMPLE
    new = sorted(records, key=lambda t: t.get("firstSeen") or "", reverse=True)[:4]
    due = sorted((t for t in records if t.get("dueDate")), key=lambda t: t["dueDate"])[:5]
    return new, due


def render(opts):
    """(subject, text, html) from the current files on disk, re-read on every request."""
    from tender_radar import notify

    importlib.reload(notify)
    new, due = sample_records()
    if "empty" in opts:
        new, due = [], []
    subject, text, html_body = notify._render(new, due, notify.DEFAULT_DASHBOARD_URL, "7")
    if "dark" in opts:
        # Pretend the viewer's mail app is in dark mode.
        html_body = html_body.replace("@media (prefers-color-scheme: dark)", "@media all")
    return subject, text, html_body


def stamp():
    return max((os.path.getmtime(p) for p in WATCHED if os.path.exists(p)), default=0)


SHELL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Email preview</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { margin: 0; font-family: system-ui, Segoe UI, sans-serif; background: #e9eef4; color: #1b2733; }
  header { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 16px;
           background: #fff; border-bottom: 1px solid #d3dce6; }
  header strong { margin-right: 8px; }
  button { font: inherit; font-size: 13px; padding: 6px 12px; border-radius: 16px; border: 1px solid #b9c7d6; background: #fff; cursor: pointer; }
  button.on { background: #0b7db8; border-color: #0b7db8; color: #fff; }
  .live { margin-left: auto; font-size: 12px; color: #4a6a85; }
  .live i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #2bb673; margin-right: 6px; }
  .subject { padding: 10px 16px; font-size: 13px; background: #f7fafc; border-bottom: 1px solid #d3dce6; }
  .stage { display: flex; justify-content: center; padding: 18px 10px 40px; }
  iframe, pre { border: 1px solid #c8d3df; border-radius: 10px; background: #fff; box-shadow: 0 8px 30px rgba(0,0,0,.08); }
  iframe { width: 760px; max-width: 100%; height: 1500px; transition: width .3s; }
  iframe.dark { background: #0b1420; }
  iframe.phone { width: 390px; }
  pre { width: 760px; max-width: 100%; padding: 18px; white-space: pre-wrap; font: 13px/1.5 Consolas, monospace; display: none; }
  body.text iframe { display: none; } body.text pre { display: block; }
</style></head>
<body>
<header>
  <strong>Email preview</strong>
  <button data-k="dark">Dark mode</button>
  <button data-k="phone">Phone width</button>
  <button data-k="empty">No tenders</button>
  <button data-k="text">Plain text</button>
  <span class="live"><i></i>Live: saves reload this page &middot; nothing is sent</span>
</header>
<div class="subject">Subject: <b id="subj"></b></div>
<div class="stage"><iframe id="f" title="Email"></iframe><pre id="t"></pre></div>
<script>
  const on = new Set(JSON.parse(localStorage.getItem('emailPreview') || '[]'));
  const f = document.getElementById('f'), t = document.getElementById('t');
  function qs() { return [...on].filter(k => k === 'dark' || k === 'empty').join('&'); }
  async function load() {
    document.body.classList.toggle('text', on.has('text'));
    f.classList.toggle('dark', on.has('dark')); f.classList.toggle('phone', on.has('phone'));
    document.querySelectorAll('button').forEach(b => b.classList.toggle('on', on.has(b.dataset.k)));
    const q = qs();
    const r = await (await fetch('/render?' + q)).json();
    document.getElementById('subj').textContent = r.subject; t.textContent = r.text;
    const y = f.contentWindow ? f.contentWindow.scrollY : 0;
    f.srcdoc = r.html;
    f.onload = () => f.contentWindow.scrollTo(0, y);
  }
  document.querySelectorAll('button').forEach(b => b.onclick = () => {
    const k = b.dataset.k; on.has(k) ? on.delete(k) : on.add(k);
    localStorage.setItem('emailPreview', JSON.stringify([...on])); load();
  });
  let last = null;
  setInterval(async () => {
    try { const s = (await (await fetch('/stamp')).json()).t; if (last !== null && s !== last) load(); last = s; } catch (e) {}
  }, 700);
  load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the terminal quiet
        pass

    def _send(self, body, ctype):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self._send(SHELL, "text/html; charset=utf-8")
        elif url.path == "/stamp":
            self._send(json.dumps({"t": stamp()}), "application/json")
        elif url.path == "/render":
            opts = set(parse_qs(url.query, keep_blank_values=True))
            try:
                subject, text, html_body = render(opts)
                payload = {"subject": subject, "text": text, "html": html_body}
            except Exception as e:  # show the mistake in the page instead of dying
                err = f"<pre style='color:#c43a3a;white-space:pre-wrap'>Could not render the email:\n{e!r}</pre>"
                payload = {"subject": "(error)", "text": repr(e), "html": err}
            self._send(json.dumps(payload), "application/json")
        else:
            self.send_error(404)


def main():
    ap = argparse.ArgumentParser(description="Live preview of the digest email (nothing is sent).")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--no-open", action="store_true", help="don't open the browser")
    args = ap.parse_args()
    os.chdir(ROOT)
    import sys
    sys.path.insert(0, ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"Email preview running at {url}  (Ctrl+C to stop). Nothing is sent.")
    if not args.no_open:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
