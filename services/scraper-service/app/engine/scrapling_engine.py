import json
from typing import Any

try:
    from scrapling.fetchers.requests import Fetcher, FetcherSession
    from scrapling.fetchers.stealth_chrome import StealthyFetcher
except ImportError:
    from scrapling.fetchers import Fetcher, FetcherSession, StealthyFetcher

from app.engine.base import IScraperEngine, ScrapedDocument


class ScraplingEngine(IScraperEngine):
    """Concrete implementation of IScraperEngine using Scrapling."""

    def __init__(self, default_impersonate: str = "chrome"):
        self.default_impersonate = default_impersonate

    def fetch(
        self,
        url: str,
        stealth: bool = False,
        network_idle: bool = True,
        wait_selector: str | None = None,
        disable_resources: bool = False,
        timeout: int = 45000,
    ) -> ScrapedDocument:
        """
        Fetches the URL.
        - stealth=True: Uses StealthyFetcher with full headless browser, network-idle waiting,
          and fingerprint spoofing to bypass Cloudflare and execute client-side JavaScript.
        - stealth=False: Uses high-performance HTTP request with Chrome TLS impersonation.
        """
        if stealth:
            kwargs: dict[str, Any] = {
                "headless": True,
                "network_idle": network_idle,
                "timeout": timeout,
            }
            if wait_selector:
                kwargs["wait_selector"] = wait_selector
            if disable_resources:
                kwargs["disable_resources"] = True

            page = StealthyFetcher.fetch(url, **kwargs)
            html_val = getattr(page, "html_content", None)
            if not html_val and hasattr(page, "body") and isinstance(page.body, (bytes, bytearray)):
                html_val = page.body.decode("utf-8", errors="ignore")
            if not html_val:
                html_val = str(getattr(page, "text", "")) or str(page)

            return ScrapedDocument(
                url=url,
                status_code=getattr(page, "status", 200),
                html=html_val,
                raw=page,
                captured_xhr=getattr(page, "captured_xhr", []),
            )
        else:
            with FetcherSession(impersonate=self.default_impersonate) as session:
                page = session.get(url, stealthy_headers=True, timeout=timeout / 1000)
                html_val = getattr(page, "html_content", None)
                if not html_val and hasattr(page, "body") and isinstance(page.body, (bytes, bytearray)):
                    html_val = page.body.decode("utf-8", errors="ignore")
                if not html_val:
                    html_val = str(getattr(page, "text", "")) or str(page)

                return ScrapedDocument(
                    url=url,
                    status_code=getattr(page, "status", 200),
                    html=html_val,
                    raw=page,
                )


    def fetch_json(self, url: str) -> dict[str, Any]:
        """Fetches a JSON endpoint using browser impersonation."""
        with FetcherSession(impersonate=self.default_impersonate) as session:
            response = session.get(url, stealthy_headers=True)
            return response.json()

