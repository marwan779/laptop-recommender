"""SovereignEG OpenAI-compatible LLM adapter (HTTP + .env loading)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

from app.domain.enrichment.models import ENRICHMENT_JSON_SCHEMA
from app.domain.enrichment.scoring import _estimate_egp_cost, _extract_json_from_llm_content

# Service root (services/ai-recommender-service) regardless of the package depth.
SCRIPT_DIR = Path(__file__).resolve().parents[2]


def load_enricher_env() -> None:
    """Load `.env` from script directory and current working directory without overriding env vars."""
    candidates = [SCRIPT_DIR / ".env", Path.cwd() / ".env"]
    seen = set()
    for p in candidates:
        rp = str(p.resolve()) if p.exists() else str(p)
        if rp in seen:
            continue
        seen.add(rp)
        if p.exists():
            load_dotenv(p, override=False)


def _call_sovereigneg_model(
    model: str,
    messages: List[Dict[str, str]],
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_sec: float = 90.0,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Call SovereignEG OpenAI-compatible `/chat/completions` for `model`.
    Handles model-specific capabilities (`supports_temperature: False` on `claude*`,
    `json_schema` structured outputs with fallback to prompt-only JSON if HTTP 400,
    and `reasoning_effort='low'` on `gpt-oss*`).
    Returns `(parsed_json_or_None, call_telemetry)`.
    """
    load_enricher_env()
    url_base = (base_url or os.getenv("ENRICHER_LLM_BASE_URL") or "").strip().rstrip("/")
    token = (api_key or os.getenv("ENRICHER_LLM_API_KEY") or "").strip()
    if not url_base or not token:
        return None, {
            "model": model,
            "latency_sec": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_egp": 0.0,
            "http_status": None,
            "error": "Missing ENRICHER_LLM_BASE_URL or ENRICHER_LLM_API_KEY",
        }

    endpoint = f"{url_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    m_low = model.lower()
    req_messages = [
        (
            {"role": m["role"], "content": str(m.get("content") or "") + "\n/no_think"}
            if "qwen" in m_low and m.get("role") == "system"
            else dict(m)
        )
        for m in messages
    ]

    if "qwen" in m_low:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": req_messages,
            "max_tokens": 4096,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }
    else:
        payload = {
            "model": model,
            "messages": req_messages,
            "max_tokens": 3000,
            "reasoning_effort": "low",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "laptop_review_enrichment",
                    "strict": True,
                    "schema": ENRICHMENT_JSON_SCHEMA,
                },
            },
        }
        if "claude" not in m_low:
            payload["temperature"] = 0.2

    t0 = time.perf_counter()
    http_status: Optional[int] = None
    last_err = ""
    resp_json: Dict[str, Any] = {}

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            http_status = resp.status_code
            # Retry selectively on HTTP 400 if provider rejects optional thinking or format params
            if resp.status_code == 400:
                err_body = resp.text.lower()
                retry_payload = dict(payload)
                changed = False
                if "chat_template_kwargs" in retry_payload and (
                    "chat_template_kwargs" in err_body
                    or "enable_thinking" in err_body
                    or "extra" in err_body
                    or "unknown" in err_body
                    or "unrecognized" in err_body
                ):
                    retry_payload.pop("chat_template_kwargs", None)
                    changed = True
                if "reasoning_effort" in err_body and "reasoning_effort" in retry_payload:
                    retry_payload.pop("reasoning_effort", None)
                    changed = True
                if "response_format" in err_body and "response_format" in retry_payload:
                    retry_payload.pop("response_format", None)
                    changed = True
                if not changed and "chat_template_kwargs" in retry_payload:
                    retry_payload.pop("chat_template_kwargs", None)
                    changed = True
                if changed:
                    resp = client.post(endpoint, headers=headers, json=retry_payload)
                    http_status = resp.status_code
            resp.raise_for_status()
            resp_json = resp.json()
    except Exception as exc:
        last_err = f"{type(exc).__name__}: {str(exc)[:240]}"
        return None, {
            "model": model,
            "latency_sec": round(time.perf_counter() - t0, 4),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_egp": 0.0,
            "http_status": http_status,
            "error": last_err,
        }

    elapsed = round(time.perf_counter() - t0, 4)
    usage = resp_json.get("usage") or {}
    ptok = int(usage.get("prompt_tokens") or 0)
    ctok = int(usage.get("completion_tokens") or 0)
    rtok = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    ttok = int(usage.get("total_tokens") or (ptok + ctok))
    cost_egp = _estimate_egp_cost(model, ptok, ctok)

    choices = resp_json.get("choices") or []
    raw_content = ""
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        raw_content = str(msg.get("content") or "").strip()

    try:
        parsed = _extract_json_from_llm_content(raw_content)
    except Exception as exc:
        return None, {
            "model": model,
            "latency_sec": elapsed,
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "reasoning_tokens": rtok,
            "total_tokens": ttok,
            "estimated_cost_egp": cost_egp,
            "http_status": http_status,
            "error": f"JSON parse failed: {type(exc).__name__}: {exc}",
        }

    return parsed, {
        "model": model,
        "latency_sec": elapsed,
        "prompt_tokens": ptok,
        "completion_tokens": ctok,
        "reasoning_tokens": rtok,
        "total_tokens": ttok,
        "estimated_cost_egp": cost_egp,
        "http_status": http_status,
        "error": None,
    }


class SovereignEGClient:
    """`ILLMClient` adapter around the SovereignEG chat-completions endpoint."""

    def __init__(self, timeout_sec: float = 90.0) -> None:
        self.timeout_sec = timeout_sec

    def call(
        self,
        model: str,
        messages: List[Dict[str, str]],
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_sec: Optional[float] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        return _call_sovereigneg_model(
            model=model,
            messages=messages,
            base_url=base_url,
            api_key=api_key,
            timeout_sec=self.timeout_sec if timeout_sec is None else timeout_sec,
        )

    def __call__(
        self,
        model: str,
        messages: List[Dict[str, str]],
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_sec: Optional[float] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        return self.call(
            model=model,
            messages=messages,
            base_url=base_url,
            api_key=api_key,
            timeout_sec=timeout_sec,
        )
