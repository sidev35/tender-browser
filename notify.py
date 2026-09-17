"""
Email digest for Tender Radar — sent from the same GitHub Actions run as
the scraper, via SendGrid's REST API (plain `requests` call, no SDK
dependency needed since scraper.py already depends on requests).

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

If any of the required three are missing, send_digest() prints why and
returns without raising — so local runs, forks, or a repo that hasn't
configured email yet don't fail because of this.
"""

import os
from datetime import datetime

import requests

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "email_template.txt")
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def _format_list(records):
    lines = []
    for t in records:
        loc = f" ({t['location']})" if t.get("location") else ""
        due = f" — due {t['dueDate']}" if t.get("dueDate") else ""
        lines.append(f"- [{t.get('category', 'Uncategorized')}] {t['desc']}{loc}{due}")
    return "\n".join(lines)


def _render(new_records, due_soon_records, dashboard_url, due_soon_days):
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        raw = f.read()

    subject_line, _, body = raw.partition("\n")
    subject = subject_line[len("Subject:"):].strip() if subject_line.startswith("Subject:") else subject_line.strip()

    new_section = (
        f"NEW TENDERS MATCHED ({len(new_records)}):\n{_format_list(new_records)}"
        if new_records else "No new tenders matched this run."
    )
    due_section = (
        f"CLOSING SOON — within {due_soon_days} days ({len(due_soon_records)}):\n{_format_list(due_soon_records)}"
        if due_soon_records else "No tenders currently closing soon."
    )

    replacements = {
        "{{NEW_COUNT}}": str(len(new_records)),
        "{{DUE_SOON_COUNT}}": str(len(due_soon_records)),
        "{{RUN_TIME}}": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "{{NEW_SECTION}}": new_section,
        "{{DUE_SOON_SECTION}}": due_section,
        "{{DASHBOARD_URL}}": dashboard_url,
    }
    for key, value in replacements.items():
        subject = subject.replace(key, value)
        body = body.replace(key, value)

    return subject, body.strip()


def send_digest(new_records, due_soon_records,
                 dashboard_url="https://sidev35.github.io/tender-browser/"):
    if not new_records and not due_soon_records:
        print("Email digest: nothing new and nothing closing soon — skipping send.")
        return

    api_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("NOTIFY_FROM_EMAIL")
    recipients = [r.strip() for r in os.environ.get("NOTIFY_RECIPIENTS", "").split(",") if r.strip()]
    due_soon_days = os.environ.get("DUE_SOON_DAYS", "7")

    if not api_key or not from_email or not recipients:
        print("Email digest: SENDGRID_API_KEY / NOTIFY_FROM_EMAIL / NOTIFY_RECIPIENTS "
              "not fully configured — skipping send. See README for setup.")
        return

    subject, body = _render(new_records, due_soon_records, dashboard_url, due_soon_days)

    payload = {
        "personalizations": [{"to": [{"email": r} for r in recipients]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    resp = requests.post(
        SENDGRID_URL,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=20,
    )
    if resp.status_code >= 300:
        print(f"  [!] SendGrid rejected the email: {resp.status_code} {resp.text}")
    else:
        print(f"Email digest sent to {len(recipients)} recipient(s): "
              f"{len(new_records)} new, {len(due_soon_records)} closing soon.")
