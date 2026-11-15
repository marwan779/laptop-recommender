"""HTTP client adapter for delegating free-text recommendations to ai-recommender-service.

Clean Architecture note: defines ``IAIRecommenderClient`` as a Protocol so
``RecommendationService`` stays decoupled from HTTP transport details and
unit tests can substitute deterministic fakes.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import logging
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.domain.recommender import PersonaType
from app.schemas.recommendation import RecommendationRequest

logger = logging.getLogger("catalog.services.ai_recommender_client")


class IAIRecommenderClient(Protocol):
    """Abstraction over remote semantic TOPSIS recommendation calls."""

    async def recommend(
        self,
        *,
        request: RecommendationRequest,
        primary_persona: PersonaType,
        blended_weights: dict[str, float] | None,
        candidate_laptops: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return raw JSON payload from ai-recommender-service, or None on fallback."""
        ...


class HttpAIRecommenderClient:
    """Async httpx client calling ai-recommender-service ``POST /recommend``."""

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

    @staticmethod
    def _build_payload(
        *,
        request: RecommendationRequest,
        primary_persona: PersonaType,
        blended_weights: dict[str, float] | None,
        candidate_laptops: list[dict[str, Any]],
    ) -> dict[str, Any]:
        persona_val = primary_persona.value if hasattr(primary_persona, "value") else str(primary_persona)
        return {
            "max_budget_egp": request.budget_egp,
            "min_budget_egp": request.min_budget_egp,
            "persona": persona_val,
            "user_text_prompt": request.user_text_prompt,
            "min_ram_gb": request.min_ram_gb,
            "min_storage_gb": request.min_storage_gb,
            "require_dgpu": request.require_dgpu,
            "brand_filter": request.brand_filter,
            "custom_weights": blended_weights,
            "top_k": request.top_k,
            "include_workloads": False,
            "candidate_laptops": candidate_laptops,
        }

    async def recommend(
        self,
        *,
        request: RecommendationRequest,
        primary_persona: PersonaType,
        blended_weights: dict[str, float] | None,
        candidate_laptops: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not self.base_url:
            return None

        url = f"{self.base_url}/recommend"
        raw_payload = self._build_payload(
            request=request,
            primary_persona=primary_persona,
            blended_weights=blended_weights,
            candidate_laptops=candidate_laptops,
        )
        payload = json.loads(json.dumps(raw_payload, default=_json_default))
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
                    "ai-recommender-service at %s rejected the request with HTTP %s. "
                    "Verify AI_RECOMMENDER_API_KEY is identical across catalog-service "
                    "and ai-recommender-service before relying on remote semantic "
                    "recommendations; falling back to local TOPSIS.",
                    url,
                    status_code,
                )
            else:
                logger.warning(
                    "ai-recommender-service call to %s failed with HTTP %s; "
                    "falling back to local TOPSIS.",
                    url,
                    status_code,
                )
            return None
        except Exception as exc:
            logger.warning(
                "ai-recommender-service call to %s failed (%s); falling back to local TOPSIS.",
                url,
                exc,
            )
            return None


def _json_default(obj: Any) -> Any:
    """Serialize datetime/date values embedded inside candidate metadata."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
