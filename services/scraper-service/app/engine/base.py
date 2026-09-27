from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScrapedDocument:
    """Standardized representation of a scraped web page."""
    url: str
    status_code: int
    html: str
    raw: Any = None
    captured_xhr: list[Any] = field(default_factory=list)

    def css(self, selector: str) -> list[Any]:
        if hasattr(self.raw, "css"):
            return self.raw.css(selector)
        return []

    def xpath(self, selector: str) -> list[Any]:
        if hasattr(self.raw, "xpath"):
            return self.raw.xpath(selector)
        return []

    def markdown(self) -> str:
        if hasattr(self.raw, "markdown"):
            return self.raw.markdown()
        return ""

    def get_meta(self, name_or_prop: str) -> str | None:
        """Extract content from <meta name=... content=...> or <meta property=... content=...>."""
        for el in self.css(f'meta[name="{name_or_prop}"], meta[property="{name_or_prop}"]'):
            content = getattr(el, "attrib", {}).get("content")
            if content:
                return content.strip()
        return None

    def get_json_ld(self) -> list[dict[str, Any]]:
        """Extract and parse all JSON-LD script blocks."""
        import json
        results = []
        for el in self.css('script[type="application/ld+json"]'):
            text = getattr(el, "text", "").strip()
            if text:
                try:
                    data = json.loads(text)
                    if isinstance(data, list):
                        results.extend(data)
                    elif isinstance(data, dict):
                        results.append(data)
                except Exception:
                    pass
        return results


class IScraperEngine(ABC):
    """Abstract interface for web scraping engines."""

    @abstractmethod
    def fetch(
        self,
        url: str,
        stealth: bool = False,
        network_idle: bool = True,
        wait_selector: str | None = None,
        disable_resources: bool = False,
        timeout: int = 45000,
    ) -> ScrapedDocument:
        """Fetches a URL and returns a standardized ScrapedDocument."""
        pass

    @abstractmethod
    def fetch_json(self, url: str) -> dict[str, Any]:
        """Fetches a JSON endpoint directly."""
        pass

