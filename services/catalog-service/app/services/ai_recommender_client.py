"""HTTP client adapter for delegating prompt scoring to ai-recommender-service.

Clean Architecture note: defines ``IAIRecommenderClient`` as a Protocol so
``RecommendationService`` stays decoupled from HTTP transport details and
unit tests can substitute deterministic fakes.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger("catalog.services.ai_recommender_client")


class IAIRecommenderClient(Protocol):
    """Abstraction over remote semantic prompt scoring."""

    async def score_prompt(self, user_text_prompt: str) -> dict[str, Any] | None:
        """Return ``{adjusted_nlp_scores, nlp_dynamic_weight, parsed_constraints}`` or None on fallback."""
        ...


class HttpAIRecommenderClient:
    """Async httpx client calling ai-recommender-service ``POST /score-prompt``."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.ai_recommender_url).rstrip("/")
        self.api_key = (api_key if api_key is not None else settings.ai_recommender_api_key).strip()
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.ai_recommender_timeout_seconds
        )
        self._client = client

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def score_prompt(self, user_text_prompt: str) -> dict[str, Any] | None:
        if not self.base_url:
            return None

        url = f"{self.base_url}/score-prompt"
        payload = {"user_text_prompt": user_text_prompt}
        headers = self._build_headers()

        try:
            if self._client is not None:
                resp = await self._client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as http_client:
                    resp = await http_client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in (401, 403, 503):
                logger.warning(
                    "ai-recommender-service at %s rejected /score-prompt with HTTP %s. "
                    "Falling back to local TOPSIS.",
                    url,
                    status_code,
                )
            else:
                logger.warning(
                    "ai-recommender-service at %s returned HTTP %s. Falling back to local TOPSIS.",
                    url,
                    status_code,
                )
            return None
        except (httpx.RequestError, ValueError, RuntimeError) as exc:
            logger.warning(
                "ai-recommender-service at %s unreachable or invalid (%s). Falling back to local TOPSIS.",
                url,
                exc,
            )
            return None
