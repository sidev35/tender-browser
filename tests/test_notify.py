"""The digest email's content (nothing is sent: only _render is called)."""

from tender_radar.notify import _render

URL = "https://sidev35.github.io/tender-browser/"


def tender(n, **extra):
    return {
        "desc": f"EV charging station tender {n}",
        "category": "Charger Supply & Installation",
        "source": "Gujarat nProcure (keyword search)",
        "dueDate": "2026-10-03",
        **extra,
    }


def test_subject_counts():
    subject, _, _ = _render([tender(1), tender(2)], [tender(3)], URL, "7")
    assert subject == "Tender Radar — 2 new match(es), 1 closing soon"


def test_plain_text_has_a_blank_line_between_tenders():
    _, text, _ = _render([tender(1), tender(2)], [], URL, "7")
    assert "- EV charging station tender 1\n  Charger Supply & Installation" in text
    assert "due 2026-10-03\n\n- EV charging station tender 2" in text


def test_plain_text_puts_the_dashboard_url_on_its_own_line():
    _, text, _ = _render([tender(1)], [], URL, "7")
    assert f"\n{URL}\n" in text


def test_html_has_a_clickable_dashboard_link():
    _, _, html_body = _render([tender(1)], [], URL, "7")
    assert f'<a href="{URL}"' in html_body
    assert "{{" not in html_body  # every placeholder filled


def test_html_shows_each_tender_as_its_own_block():
    _, _, html_body = _render([tender(1), tender(2)], [tender(3)], URL, "7")
    # Exactly once each: a placeholder written in the template's own comment
    # used to get filled in too, duplicating every tender inside the comment.
    assert html_body.count("border-left: 3px solid") == 3
    assert html_body.count("EV charging station tender 1") == 1


def test_scraped_text_is_escaped_in_html():
    _, _, html_body = _render([tender(1, desc="Supply <b>& install</b> chargers")], [], URL, "7")
    assert "Supply &lt;b&gt;&amp; install&lt;/b&gt; chargers" in html_body
    assert "<b>& install" not in html_body


def test_value_and_location_are_shown_when_known():
    _, text, _ = _render([tender(1, value="₹2.55 Cr", location="Gujarat")], [], URL, "7")
    assert "Gujarat · due 2026-10-03 · ₹2.55 Cr" in text


def test_empty_sections_say_so():
    _, text, html_body = _render([], [tender(1)], URL, "7")
    assert "No new tenders matched this run." in text
    assert "No new tenders matched this run." in html_body


def test_closing_soon_shows_ten_soonest_then_a_more_link():
    due = [tender(n, dueDate=f"2026-10-{n:02d}") for n in range(25, 0, -1)]
    _, text, html_body = _render([], due, URL, "7")
    assert "CLOSING SOON — within 7 days (25):" in text
    assert text.count("- EV charging station tender") == 10
    assert "due 2026-10-01" in text and "due 2026-10-10" in text and "due 2026-10-11" not in text
    assert "+ 15 more closing soon" in text
    assert html_body.count("border-left: 3px solid") == 10
    assert f'<a href="{URL}" style="color: #0f9d63; font-weight: bold;">+ 15 more' in html_body


def test_no_more_link_when_ten_or_fewer_are_closing_soon():
    _, text, html_body = _render([], [tender(n) for n in range(10)], URL, "7")
    assert "more closing soon" not in text
    assert "more — see all" not in html_body
