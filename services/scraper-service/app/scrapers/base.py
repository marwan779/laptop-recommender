from abc import ABC, abstractmethod

from app.engine.base import IScraperEngine
from app.schemas.laptop import ConfigurationItem, LaptopDetail, LaptopSummary, SkippedLaptop


class BaseBrandScraper(ABC):
    """Abstract base class for brand-specific laptop scrapers."""

    def __init__(self, engine: IScraperEngine | None = None):
        self.engine = engine
        self.skipped_laptops: list[SkippedLaptop] = []

    def record_skipped(
        self,
        name: str,
        reason: str,
        url: str | None = None,
        error: str | None = None,
        stage: str | None = None,
    ) -> None:
        """Record a skipped laptop for debugging and observability."""
        self.skipped_laptops.append(
            SkippedLaptop(
                name=name,
                url=url,
                reason=reason,
                error=error,
                stage=stage,
            )
        )

    @property
    @abstractmethod
    def brand_name(self) -> str:
        pass

    @property
    @abstractmethod
    def catalog_url(self) -> str:
        pass

    @abstractmethod
    def get_laptop_summaries(
        self,
        limit: int | None = None,
        until_model: str | list[str] | None = None,
        max_pages: int | None = None,
    ) -> list[LaptopSummary]:
        pass

    @abstractmethod
    def get_laptop_detail(
        self,
        summary: LaptopSummary,
    ) -> LaptopDetail | None:
        """Fetch deep specifications. Returns None if the model is an unreleased placeholder."""
        pass

    def extract_configurations(self, detail: LaptopDetail) -> list[ConfigurationItem]:
        """Expand a LaptopDetail into distinct official ConfigurationItems."""
        return [
            ConfigurationItem(
                model=detail.model or "UNKNOWN",
                model_series=detail.model,
                base_model=detail.base_model or detail.model,
                mpn=detail.sku_part_number,
                official_specs=detail.all_specs,
                stores=[],
            )
        ]
