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
import re
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
    # Drop the trailing "(...)" note sources.json names carry (how the portal
    # is read, e.g. "(keyword search)"); the reader only needs the portal.
    source = re.sub(r"\s*\([^)]*\)\s*$", "", t.get("source") or "")
    parts = [t.get("category") or "Uncategorized", source]
    if t.get("location"):
        parts.append(t["location"])
    if t.get("dueDate"):
        parts.append(f"due {t['dueDate']}" + (f" {t['dueTime']}" if t.get("dueTime") else ""))
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
        block = f"- {t['desc'].lstrip(' .…')}\n  {_details(t)}"
        if url := _link(t):
            label = "Tender" if _is_direct(t) else "Portal (search for the title)"
            block += f"\n  {label}: {url}"
        blocks.append(block)
    return "\n\n".join(blocks)


def _details_parts(t):
    """(category, [other details], due text or None) for the HTML card."""
    source = re.sub(r"\s*\([^)]*\)\s*$", "", t.get("source") or "")
    rest = [p for p in (source, t.get("location"), t.get("value")) if p]
    due = None
    if t.get("dueDate"):
        due = f"due {t['dueDate']}" + (f" {t['dueTime']}" if t.get("dueTime") else "")
    return t.get("category") or "Uncategorized", rest, due


BORDER = "rgba(128, 128, 128, .35)"  # a translucent grey: visible on a light or a dark mail theme


def _format_list_html(records, kind="new"):
    """HTML: one bordered card per tender (category, the title linking to the
    portal, then source / state / due / value). No colours are set, so the
    reader's mail app (light or dark) supplies them. Scraped text is escaped."""
    # New tenders get a stronger left edge than closing-soon ones.
    edge = "rgba(128, 128, 128, .85)" if kind == "new" else "rgba(128, 128, 128, .45)"

    def title(t):
        text = html.escape(t["desc"].lstrip(" .…"))
        if url := _link(t):
            href = html.escape(url, quote=True)
            return f'<a href="{href}" style="text-decoration: underline;">{text}</a>'
        return text

    def note(t):
        if _link(t) and not _is_direct(t):
            return (
                '<div style="font-size: 12px; opacity: .7; margin-top: 6px;">'
                "Opens the portal's search page — search for this title there.</div>"
            )
        return ""

    def card(i, t):
        category, rest, due = _details_parts(t)
        badge = (
            f' <span class="tr-new" style="display: inline-block; vertical-align: middle; margin-left: 6px; padding: 0 7px; '
            f"border: 1px solid {edge}; border-radius: 10px; font-size: 10px; font-weight: 700; letter-spacing: .06em;\">NEW</span>"
            if kind == "new"
            else ""
        )
        meta = " &middot; ".join(html.escape(p) for p in rest)
        if due:
            due_html = f'<strong>{html.escape(due)}</strong>' if kind == "due" else html.escape(due)
            meta = f"{meta} &middot; {due_html}" if meta else due_html
        return (
            f'<div class="tr-card tr-d{min(i + 1, 6)}" style="margin: 0 0 12px; padding: 12px 14px; '
            f"border: 1px solid {BORDER}; border-left: 3px solid {edge}; border-radius: 10px;\">"
            '<div style="margin-bottom: 5px;">'
            f'<span style="display: inline-block; padding: 0 9px; border: 1px solid {BORDER}; border-radius: 10px; '
            f'font-size: 11px; font-weight: 600;">{html.escape(category)}</span>{badge}</div>'
            f'<div style="font-weight: 600; font-size: 14.5px; line-height: 1.4;">{title(t)}</div>'
            f'<div style="font-size: 12.5px; opacity: .7; margin-top: 5px;">{meta}</div>'
            f"{note(t)}"
            "</div>"
        )

    return "\n".join(card(i, t) for i, t in enumerate(records))


def _more_text(hidden, dashboard_url):
    return f"+ {hidden} more closing soon — see all on the dashboard:\n{dashboard_url}"


def _more_html(hidden, dashboard_url):
    return (
        '<p style="margin: 0 0 14px;">'
        f'<a href="{html.escape(dashboard_url, quote=True)}" style="font-weight: bold;">'
        f"+ {hidden} more — see all on the dashboard &rarr;</a></p>"
    )


def _section_heading_html(text, count=None, kind="new", sub=None):
    """A plain heading with a small count pill."""
    pill = (
        f'<span style="display: inline-block; vertical-align: middle; margin-left: 8px; padding: 0 9px; '
        f'border: 1px solid {BORDER}; border-radius: 12px; font-size: 12px; font-weight: 600;">{count}</span>'
        if count is not None
        else ""
    )
    subtext = f'<span style="font-size: 12px; font-weight: 400; opacity: .7; margin-left: 8px;">{html.escape(sub)}</span>' if sub else ""
    return f'<h3 style="font-size: 16px; margin: 24px 0 12px;">{html.escape(text)}{pill}{subtext}</h3>'


def _empty_html(text):
    return (
        f'<div style="margin: 0 0 12px; padding: 14px 16px; border: 1px dashed {BORDER}; border-radius: 10px; '
        f'font-size: 13px; opacity: .75;">{html.escape(text)}</div>'
    )


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
                _section_heading_html("New tenders matched", len(new_records), "new")
                + _format_list_html(new_records, "new")
                if new_records
                else _empty_html(no_new)
            ),
            "{{DUE_SOON_SECTION}}": (
                _section_heading_html("Closing soon", total_due, "due", sub=f"within {due_soon_days} days")
                + _format_list_html(shown_due, "due")
                + (_more_html(hidden_due, dashboard_url) if hidden_due else "")
                if due_soon_records
                else _empty_html(no_due)
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
