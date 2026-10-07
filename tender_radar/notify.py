"""
Email digest for Tender Radar — sent from the same GitHub Actions run as
the scraper, via plain SMTP (stdlib `smtplib`, no extra dependency).

This repo is public, so nothing sensitive or personal lives in it.
Everything here is configured entirely through environment variables,
set as GitHub Actions secrets/variables in the workflow:

    SMTP_HOST          - SMTP server hostname (repo VARIABLE)
    SMTP_PORT          - SMTP port, defaults to 587 (repo VARIABLE)
    SMTP_USERNAME      - SMTP login (repo SECRET)
    SMTP_PASSWORD      - SMTP password (repo SECRET)
    SMTP_ENABLE_SSL    - "true" (default) to encrypt the connection: implicit
                         SSL on port 465, STARTTLS on any other port;
                         "false" for a plain connection (repo VARIABLE)
    NOTIFY_FROM_EMAIL  - sender address, i.e. the EmailFrom of the SMTP
                         account (repo VARIABLE)
    NOTIFY_RECIPIENTS  - comma-separated recipient addresses (repo VARIABLE)
    DASHBOARD_URL      - optional, the dashboard link in the email (repo VARIABLE,
                         defaults to the sidev35 GitHub Pages site)
    DUE_SOON_DAYS      - optional override of the "closing soon" window
                         in days (repo VARIABLE, defaults to 7)
    MIN_HOURS_BETWEEN_DIGESTS - optional, defaults to 6 (repo VARIABLE)

If any of the required settings (host, username, password, from, recipients) are missing, send_digest() prints why and
returns without raising — so local runs, forks, or a repo that hasn't
configured email yet don't fail because of this.

The scraper runs every 15 minutes (to catch each portal's rotating
"latest 10" homepage widget before it scrolls off), but emailing that
often would spam the inbox and hit the SMTP account's sending limits — especially since "closing soon" tenders are re-included in every
digest until they close. MIN_HOURS_BETWEEN_DIGESTS throttles actual
sends to at most once per that many hours, tracked in digest_state.json
(committed alongside docs/data/tenders.json), regardless of how often
the scraper itself runs and updates the dashboard.
"""

import html
import json
import logging
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any

log = logging.getLogger(__name__)

# Both live at the repo root (one level above this package); the workflow
# commits digest_state.json from there.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(REPO_ROOT, "email_template.txt")
# HTML version, shown by mail apps (clickable link, spaced-out tenders); the
# plain text above is the fallback. Optional: without it, only text is sent.
HTML_TEMPLATE_PATH = os.path.join(REPO_ROOT, "email_template.html")
DIGEST_STATE_PATH = os.path.join(REPO_ROOT, "digest_state.json")

DEFAULT_DASHBOARD_URL = "https://sidev35.github.io/tender-browser/"
# The closing-soon list shows this many tenders (soonest due first); the rest
# become one "+N more" link to the dashboard.
MAX_CLOSING_SOON = 10


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


def _link(t):
    """The tender's portal link, only if it is a web address (scraped text is untrusted)."""
    url = (t.get("url") or "").strip()
    return url if url.startswith(("http://", "https://")) else None


def _is_direct(t):
    """Same split as the dashboard: a direct link opens the tender itself, any other
    opens the portal's search/listing page, where the title has to be searched."""
    return t.get("linkType") == "direct"


def _format_list(records):
    """Plain text: one tender per block, with a blank line between tenders."""
    blocks = []
    for t in records:
        block = f"- {t['desc']}\n  {_details(t)}"
        if url := _link(t):
            label = "Tender" if _is_direct(t) else "Portal (search for the title)"
            block += f"\n  {label}: {url}"
        blocks.append(block)
    return "\n\n".join(blocks)


def _format_list_html(records):
    """HTML: one spaced-out block per tender, the title linking to the portal.
    Scraped text is escaped."""
    def title(t):
        text = html.escape(t["desc"])
        if url := _link(t):
            href = html.escape(url, quote=True)
            return f'<a href="{href}" style="color: #0b6e45; text-decoration: underline;">{text}</a>'
        return text

    def note(t):
        if _link(t) and not _is_direct(t):
            return (
                '<div style="color: #59695f; font-size: 12px; margin-top: 4px;">'
                "Opens the portal's search page — search for this title there.</div>"
            )
        return ""

    return "\n".join(
        '<div style="margin: 0 0 14px; padding: 10px 12px; border-left: 3px solid #0f9d63; '
        'background: #f5f8f6;">'
        f'<div style="font-weight: bold;">{title(t)}</div>'
        f'<div style="color: #59695f; font-size: 13px; margin-top: 4px;">{html.escape(_details(t))}</div>'
        f"{note(t)}"
        "</div>"
        for t in records
    )


def _more_text(hidden, dashboard_url):
    return f"+ {hidden} more closing soon — see all on the dashboard:\n{dashboard_url}"


def _more_html(hidden, dashboard_url):
    return (
        '<p style="margin: 0 0 14px;">'
        f'<a href="{html.escape(dashboard_url, quote=True)}" style="color: #0f9d63; font-weight: bold;">'
        f"+ {hidden} more — see all on the dashboard &rarr;</a></p>"
    )


def _section_heading_html(text):
    return f'<h3 style="font-size: 15px; margin: 24px 0 10px;">{html.escape(text)}</h3>'


def _render(new_records, due_soon_records, dashboard_url, due_soon_days):
    """Returns (subject, plain-text body, HTML body or None)."""
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        raw = f.read()

    # Headings keep the full count; only the list is cut, soonest due first.
    total_due = len(due_soon_records)
    shown_due = sorted(due_soon_records, key=lambda t: t.get("dueDate") or "9999")[:MAX_CLOSING_SOON]
    hidden_due = total_due - len(shown_due)

    subject_line, _, body = raw.partition("\n")
    subject = subject_line.removeprefix("Subject:").strip()

    new_heading = f"NEW TENDERS MATCHED ({len(new_records)}):"
    due_heading = f"CLOSING SOON — within {due_soon_days} days ({total_due}):"
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
            f"{due_heading}\n\n{_format_list(shown_due)}"
            + (f"\n\n{_more_text(hidden_due, dashboard_url)}" if hidden_due else "")
            if due_soon_records
            else no_due
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
                _section_heading_html(due_heading)
                + _format_list_html(shown_due)
                + (_more_html(hidden_due, dashboard_url) if hidden_due else "")
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
    dashboard_url: str | None = None,
) -> None:
    if not new_records and not due_soon_records:
        log.info("Email digest: nothing new and nothing closing soon — skipping send.")
        return

    dashboard_url = dashboard_url or os.environ.get("DASHBOARD_URL") or DEFAULT_DASHBOARD_URL
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

    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT") or "587")
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    enable_ssl = (os.environ.get("SMTP_ENABLE_SSL") or "true").strip().lower() not in ("0", "false", "no")
    from_email = os.environ.get("NOTIFY_FROM_EMAIL")
    recipients = [r.strip() for r in os.environ.get("NOTIFY_RECIPIENTS", "").split(",") if r.strip()]
    due_soon_days = os.environ.get("DUE_SOON_DAYS") or "7"

    if not host or not username or not password or not from_email or not recipients:
        log.info(
            "Email digest: SMTP_HOST / SMTP_USERNAME / SMTP_PASSWORD / NOTIFY_FROM_EMAIL / "
            "NOTIFY_RECIPIENTS not fully configured — skipping send. See README for setup."
        )
        return

    subject, body, html_body = _render(new_records, due_soon_records, dashboard_url, due_soon_days)

    # Plain text first; mail apps show the HTML alternative if there is one
    # and fall back to the text.
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        if enable_ssl and port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        with server:
            if enable_ssl and port != 465:
                server.starttls()
            server.login(username, password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        log.warning(f"  [!] SMTP send failed: {e!r}")
        return

    _record_sent(now)
    log.info(
        f"Email digest sent to {len(recipients)} recipient(s): "
        f"{len(new_records)} new, {len(due_soon_records)} closing soon."
    )
