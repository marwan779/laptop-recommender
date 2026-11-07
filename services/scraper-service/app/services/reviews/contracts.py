"""Abstract contracts for chassis review collection (Pattern B).

Collectors receive the raw ``LaptopReviewTarget`` list and return **pure platform
mappings** keyed by chassis key. They never receive or construct the S3 root
artifact, and they never touch object storage — only the orchestrator persists.

This keeps each collector a single-responsibility data producer:

    IYouTubeReviewsCollector.collect_for_targets  -> dict[chassis_key, YouTubeReviewData]
    ICommunitiesReviewsCollector.collect_for_targets -> dict[chassis_key, CommunitiesData]

The contracts stay narrow (Interface Segregation) and depend on abstractions
(Dependency Inversion), so concrete collectors can be swapped, mocked, or added
(e.g. TikTok) without changing orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.events import LaptopReviewTarget
from app.schemas.reviews_s3 import CommunitiesData, YouTubeReviewData


class IYouTubeReviewsCollector(ABC):
    """Contract for collecting YouTube review evidence for each chassis target."""

    @abstractmethod
    async def collect_for_targets(
        self,
        targets: list[LaptopReviewTarget],
    ) -> dict[str, YouTubeReviewData]:
        """Collect YouTube review data for every target.

        Returns:
            A mapping from ``chassis_key`` -> ``YouTubeReviewData``.
        """
        ...


class ICommunitiesReviewsCollector(ABC):
    """Contract for collecting community (Reddit, Facebook, ...) review evidence."""

    @abstractmethod
    async def collect_for_targets(
        self,
        targets: list[LaptopReviewTarget],
    ) -> dict[str, CommunitiesData]:
        """Collect community platform review data for every target.

        Returns:
            A mapping from ``chassis_key`` -> ``CommunitiesData``.
        """
        ...


class StubYouTubeReviewsCollector(IYouTubeReviewsCollector):
    """No-op YouTube collector returning an empty mapping.

    Used as a test double and as a safe placeholder when the concrete pipeline is
    intentionally disabled.
    """

    async def collect_for_targets(
        self,
        targets: list[LaptopReviewTarget],
    ) -> dict[str, YouTubeReviewData]:
        return {}


class StubCommunitiesReviewsCollector(ICommunitiesReviewsCollector):
    """No-op communities collector returning an empty mapping."""

    async def collect_for_targets(
        self,
        targets: list[LaptopReviewTarget],
    ) -> dict[str, CommunitiesData]:
        return {}


__all__ = [
    "ICommunitiesReviewsCollector",
    "IYouTubeReviewsCollector",
    "StubCommunitiesReviewsCollector",
    "StubYouTubeReviewsCollector",
]
