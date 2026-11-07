"""Abstract contracts for chassis review collection.

Enforces Dependency Inversion: the orchestrator depends on these narrow
interfaces rather than concrete YouTube/community scrapers. Concrete collectors
can be swapped, mocked, or extended (e.g. TikTok, forums) without touching the
orchestration logic.

Both collectors mutate-or-return the same ``LaptopChassisReviewItem`` list, which
keeps the pipeline a simple sequential fold.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.reviews_s3 import LaptopChassisReviewItem


class IYouTubeReviewsCollector(ABC):
    """Contract for collecting YouTube review evidence for chassis items."""

    @abstractmethod
    async def collect(
        self,
        items: list[LaptopChassisReviewItem],
    ) -> list[LaptopChassisReviewItem]:
        """Enrich each item's ``youtube`` section and return the list.

        Implementations must preserve item order and must not drop items.
        """
        ...


class ICommunitiesReviewsCollector(ABC):
    """Contract for collecting community (Reddit, Facebook, ...) evidence."""

    @abstractmethod
    async def collect(
        self,
        items: list[LaptopChassisReviewItem],
    ) -> list[LaptopChassisReviewItem]:
        """Enrich each item's ``communities`` section and return the list.

        Implementations must preserve item order and must not drop items.
        """
        ...


class StubYouTubeReviewsCollector(IYouTubeReviewsCollector):
    """No-op YouTube collector.

    Returns items unchanged, leaving each ``youtube`` field at its initialized
    (empty) value. Used until the real YouTube collector is implemented.
    """

    async def collect(
        self,
        items: list[LaptopChassisReviewItem],
    ) -> list[LaptopChassisReviewItem]:
        return items


class StubCommunitiesReviewsCollector(ICommunitiesReviewsCollector):
    """No-op communities collector.

    Returns items unchanged, leaving each ``communities`` field at its
    initialized (empty) value.
    """

    async def collect(
        self,
        items: list[LaptopChassisReviewItem],
    ) -> list[LaptopChassisReviewItem]:
        return items


__all__ = [
    "ICommunitiesReviewsCollector",
    "IYouTubeReviewsCollector",
    "StubCommunitiesReviewsCollector",
    "StubYouTubeReviewsCollector",
]
