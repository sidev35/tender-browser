"""
The headless browser every source is loaded through (Playwright).

One browser is started per scraper run and shared by every source; each
source gets a fresh browser context, so cookies/sessions never leak between
portals. Images, fonts and media are blocked, so each site only serves the
HTML documents and scripts it needs to show its listing.
"""

import logging
import os
from typing import Any

from playwright.sync_api import Page, sync_playwright

from .config import USER_AGENT

log = logging.getLogger(__name__)


def playwright_launch_kwargs() -> dict[str, Any]:
    """
    Headless launch options for p.chromium.launch(). Defaults to driving the
    system's installed Microsoft Edge (channel "msedge"), because this
    machine's network blocks Playwright's own Chromium download
    (cdn.playwright.dev). Without that default, a plain `python scraper.py`
    tried the never-downloaded bundled Chromium and failed with Playwright's
    "please run `playwright install`" banner.
    Set PLAYWRIGHT_CHROMIUM_CHANNEL=chromium to use the bundled Chromium
    instead; the GitHub Actions workflow does this, since its runner
    installs that browser. Any other value is passed through as the channel
    (e.g. "chrome").
    """
    channel = (os.environ.get("PLAYWRIGHT_CHROMIUM_CHANNEL") or "msedge").strip()
    kwargs = {"headless": True}
    if channel.lower() != "chromium":
        kwargs["channel"] = channel
    return kwargs


# Resource types never needed to read a tender listing. Blocking them keeps
# each page load close to "just the HTML", which is kinder to the portals and
# faster than a full browser page load. Stylesheets are NOT blocked: the
# interactive-search selectors rely on :visible, which needs real layout.
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


def _block_heavy_resources(route):
    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
        route.abort()
    else:
        route.continue_()


class BrowserSession:
    """
    One headless browser for a whole scraper run, shared by every source.
    Each source gets its own fresh browser context (clean cookies/session),
    so sources can't affect each other.

        with BrowserSession() as session:
            html = session.get_html(url)
    """

    def start(self) -> "BrowserSession":
        self._playwright = sync_playwright().start()
        try:
            self.browser = self._playwright.chromium.launch(**playwright_launch_kwargs())
        except Exception:
            self._playwright.stop()
            raise
        return self

    def close(self) -> None:
        try:
            self.browser.close()
        finally:
            self._playwright.stop()

    def __enter__(self) -> "BrowserSession":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def open(self, url: str, wait_until: str = "domcontentloaded", settle_ms: int = 0) -> Page | None:
        """
        Loads url in a new page and returns that page, or None on failure.
        The caller must close it with page.context.close().

        Some Indian government sites (and some corporate/ISP networks with SSL
        inspection) present certificate chains the browser rejects, even
        though the site is legitimate. A verified load is tried first; only
        if that fails on a certificate error is it retried without
        verification, and that is said loudly rather than done silently.
        """
        for insecure in (False, True):
            context = self.browser.new_context(user_agent=USER_AGENT, ignore_https_errors=insecure)
            context.route("**/*", _block_heavy_resources)
            page = context.new_page()
            try:
                resp = page.goto(url, timeout=30000, wait_until=wait_until)
                if resp is not None and resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status}")
                if settle_ms:
                    page.wait_for_timeout(settle_ms)
                return page
            except Exception as e:
                context.close()
                if not insecure and ("ERR_CERT" in str(e) or "ERR_SSL" in str(e)):
                    log.warning(
                        f"  [!] SSL verification failed for {url} — retrying without verification.\n"
                        "      This usually means your network (ISP/office firewall) is intercepting\n"
                        "      HTTPS traffic, or the government site's cert chain is misconfigured.\n"
                        "      Only do this if you trust the network you're on."
                    )
                    continue
                log.warning(f"  [!] Could not load {url}: {e}")
                return None
        return None

    def get_html(self, url: str, wait_until: str = "domcontentloaded", settle_ms: int = 0) -> str | None:
        """Loads url and returns the rendered HTML, or None on failure."""
        page = self.open(url, wait_until=wait_until, settle_ms=settle_ms)
        if page is None:
            return None
        try:
            return page.content()
        finally:
            page.context.close()
