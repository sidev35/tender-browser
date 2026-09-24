"""
Email digest for Tender Radar — sent from the same GitHub Actions run as
the scraper, via SendGrid's REST API (plain `requests` call, no SDK
dependency needed).

This repo is public, so nothing sensitive or personal lives in it.
Everything here is configured entirely through environment variables,
set as GitHub Actions secrets/variables in the workflow:

    SENDGRID_API_KEY   - SendGrid API key (repo SECRET)
    NOTIFY_FROM_EMAIL  - sender address; must be a verified SendGrid
                         sender (repo VARIABLE — not sensitive, but
                         must match what you verified in SendGrid)
    NOTIFY_RECIPIENTS  - comma-separated recipient addresses (repo VARIABLE)
    DUE_SOON_DAYS      - optional override of the "closing soon" window
                         in days (repo VARIABLE, defaults to 7)
    MIN_HOURS_BETWEEN_DIGESTS - optional, defaults to 6 (repo VARIABLE)

If any of the required three are missing, send_digest() prints why and
returns without raising — so local runs, forks, or a repo that hasn't
configured email yet don't fail because of this.

The scraper runs every 15 minutes (to catch each portal's rotating
"latest 10" homepage widget before it scrolls off), but emailing that
often would spam the inbox and blow through SendGrid's free-tier daily
cap — especially since "closing soon" tenders are re-included in every
digest until they close. MIN_HOURS_BETWEEN_DIGESTS throttles actual
sends to at most once per that many hours, tracked in digest_state.json
(committed alongside docs/data/tenders.json), regardless of how often
the scraper itself runs and updates the dashboard.
"""

import html
import json
import logging
import os
from datetime import datetime
from typing import Any

import requests

log = logging.getLogger(__name__)

# Both live at the repo root (one level above this package); the workflow
# commits digest_state.json from there.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(REPO_ROOT, "email_template.txt")
# HTML version, shown by mail apps (clickable link, spaced-out tenders); the
# plain text above is the fallback. Optional: without it, only text is sent.
HTML_TEMPLATE_PATH = os.path.join(REPO_ROOT, "email_template.html")
DIGEST_STATE_PATH = os.path.join(REPO_ROOT, "digest_state.json")
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def _last_sent():
    try:
        with open(DIGEST_STATE_PATH, encoding="utf-8") as f:
            return datetime.fromisoformat(json.load(f)["last_sent"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _record_sent(when):
    with open(DIGEST_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump({"last_sent": when.isoformat()}, f)


def _details(t):
    """ "Category · Source · due 2026-10-03 · ₹2.55 Cr" for one tender."""
    parts = [t.get("category") or "Uncategorized", t.get("source")]
    if t.get("location"):
        parts.append(t["location"])
    if t.get("dueDate"):
        parts.append(f"due {t['dueDate']}")
    if t.get("value"):
        parts.append(t["value"])
    return " · ".join(p for p in parts if p)


def _format_list(records):
    """Plain text: one tender per block, with a blank line between tenders."""
    return "\n\n".join(f"- {t['desc']}\n  {_details(t)}" for t in records)


def _format_list_html(records):
    """HTML: one spaced-out block per tender. Scraped text is escaped."""
    return "\n".join(
        '<div style="margin: 0 0 14px; padding: 10px 12px; border-left: 3px solid #0f9d63; '
        'background: #f5f8f6;">'
        f'<div style="font-weight: bold;">{html.escape(t["desc"])}</div>'
        f'<div style="color: #59695f; font-size: 13px; margin-top: 4px;">{html.escape(_details(t))}</div>'
        "</div>"
        for t in records
    )


def _section_heading_html(text):
    return f'<h3 style="font-size: 15px; margin: 24px 0 10px;">{html.escape(text)}</h3>'


def _render(new_records, due_soon_records, dashboard_url, due_soon_days):
    """Returns (subject, plain-text body, HTML body or None)."""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        raw = f.read()

    subject_line, _, body = raw.partition("\n")
    subject = subject_line.removeprefix("Subject:").strip()

    new_heading = f"NEW TENDERS MATCHED ({len(new_records)}):"
    due_heading = f"CLOSING SOON — within {due_soon_days} days ({len(due_soon_records)}):"
    no_new, no_due = "No new tenders matched this run.", "No tenders currently closing soon."

    common = {
        "{{NEW_COUNT}}": str(len(new_records)),
        "{{DUE_SOON_COUNT}}": str(len(due_soon_records)),
        "{{RUN_TIME}}": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    text = {
        **common,
        "{{NEW_SECTION}}": f"{new_heading}\n\n{_format_list(new_records)}" if new_records else no_new,
        "{{DUE_SOON_SECTION}}": (
            f"{due_heading}\n\n{_format_list(due_soon_records)}" if due_soon_records else no_due
        ),
        "{{DASHBOARD_URL}}": dashboard_url,
    }
    for key, value in text.items():
        subject = subject.replace(key, value)
        body = body.replace(key, value)

    html_body = None
    if os.path.exists(HTML_TEMPLATE_PATH):
        with open(HTML_TEMPLATE_PATH, encoding="utf-8") as f:
            html_body = f.read()
        rich = {
            **common,
            "{{NEW_SECTION}}": (
                _section_heading_html(new_heading) + _format_list_html(new_records)
                if new_records
                else f"<p>{no_new}</p>"
            ),
            "{{DUE_SOON_SECTION}}": (
                _section_heading_html(due_heading) + _format_list_html(due_soon_records)
                if due_soon_records
                else f"<p>{no_due}</p>"
            ),
            "{{DASHBOARD_URL}}": html.escape(dashboard_url, quote=True),
        }
        for key, value in rich.items():
            html_body = html_body.replace(key, value)

    return subject, body.strip(), html_body


def send_digest(
    new_records: list[dict[str, Any]],
    due_soon_records: list[dict[str, Any]],
    dashboard_url: str = "https://sidev35.github.io/tender-browser/",
) -> None:
    if not new_records and not due_soon_records:
        log.info("Email digest: nothing new and nothing closing soon — skipping send.")
        return

    min_hours = float(os.environ.get("MIN_HOURS_BETWEEN_DIGESTS") or "6")
    last_sent = _last_sent()
    now = datetime.now()
    if last_sent is not None:
        elapsed_hours = (now - last_sent).total_seconds() / 3600
        if elapsed_hours < min_hours:
            log.info(
                f"Email digest: last one sent {elapsed_hours:.1f}h ago, under the "
                f"{min_hours}h minimum gap — skipping to avoid spamming the inbox. "
                f"(The dashboard data itself was still updated this run.)"
            )
            return

    api_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("NOTIFY_FROM_EMAIL")
    recipients = [r.strip() for r in os.environ.get("NOTIFY_RECIPIENTS", "").split(",") if r.strip()]
    due_soon_days = os.environ.get("DUE_SOON_DAYS") or "7"

    if not api_key or not from_email or not recipients:
        log.info(
            "Email digest: SENDGRID_API_KEY / NOTIFY_FROM_EMAIL / NOTIFY_RECIPIENTS "
            "not fully configured — skipping send. See README for setup."
        )
        return

    subject, body, html_body = _render(new_records, due_soon_records, dashboard_url, due_soon_days)

    # SendGrid requires text/plain first; mail apps show the HTML part if
    # there is one and fall back to the text.
    content = [{"type": "text/plain", "value": body}]
    if html_body:
        content.append({"type": "text/html", "value": html_body})
    payload = {
        "personalizations": [{"to": [{"email": r} for r in recipients]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": content,
    }
    resp = requests.post(
        SENDGRID_URL,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=20,
    )
    if resp.status_code >= 300:
        log.warning(f"  [!] SendGrid rejected the email: {resp.status_code} {resp.text}")
    else:
        _record_sent(now)
        log.info(
            f"Email digest sent to {len(recipients)} recipient(s): "
            f"{len(new_records)} new, {len(due_soon_records)} closing soon."
        )
