"""Unit tests for SovereignEG dual-key credit failover and model fallback."""

from __future__ import annotations

import json
import httpx

from app.core.sovereign_config import SovereignConfig
from app.infrastructure.sovereigneg_client import SovereignEGClient


def _ok_body(payload: dict) -> dict:
    return {
        "choices": [{"message": {"content": json.dumps(payload)}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 45},
    }


def test_primary_key_succeeds_without_touching_fallback() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        calls.append((request.headers["Authorization"], body["model"]))
        return httpx.Response(200, json=_ok_body({"memory": {"capacity_gb": 16}}))

    client = SovereignEGClient(
        config=SovereignConfig(
            base_url="https://backend.sovereigneg.com/v1",
            primary_api_key="sk-primary",
            fallback_api_key="sk-fallback",
            max_transient_retries=0,
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    parsed, tel = client.complete_json([{"role": "user", "content": "hi"}])
    assert parsed == {"memory": {"capacity_gb": 16}}
    assert calls == [("Bearer sk-primary", "claude-haiku-5.5")]
    assert tel.key_slot_used == "primary"
    assert tel.primary_key_exhausted is False


def test_credit_exhaustion_switches_to_fallback_key_for_rest_of_run() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers["Authorization"]
        model = json.loads(request.content.decode("utf-8"))["model"]
        calls.append((auth, model))
        if auth == "Bearer sk-primary":
            return httpx.Response(402, json={"error": {"message": "Insufficient credits on account"}})
        return httpx.Response(200, json=_ok_body({"storage": {"slot_count": 2}}))

    client = SovereignEGClient(
        config=SovereignConfig(
            base_url="https://backend.sovereigneg.com/v1",
            primary_api_key="sk-primary",
            fallback_api_key="sk-fallback",
            max_transient_retries=1,
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    parsed1, tel1 = client.complete_json([{"role": "user", "content": "one"}])
    assert parsed1 == {"storage": {"slot_count": 2}}
    assert tel1.primary_key_exhausted is True
    assert tel1.key_slot_used == "fallback"

    # Second call must skip sk-primary completely and hit sk-fallback immediately
    parsed2, tel2 = client.complete_json([{"role": "user", "content": "two"}])
    assert parsed2 == {"storage": {"slot_count": 2}}
    assert tel2.key_slot_used == "fallback"
    assert calls == [
        ("Bearer sk-primary", "claude-haiku-5.5"),
        ("Bearer sk-fallback", "claude-haiku-5.5"),
        ("Bearer sk-fallback", "claude-haiku-5.5"),
    ]


def test_falls_back_to_gpt_oss_when_haiku_fails_on_both_keys() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers["Authorization"]
        model = json.loads(request.content.decode("utf-8"))["model"]
        calls.append((auth, model))
        if model == "claude-haiku-5.5":
            return httpx.Response(200, json={"choices": [{"message": {"content": "not valid json"}}]})
        return httpx.Response(200, json=_ok_body({"build_security": {"has_backlit_keyboard": True}}))

    client = SovereignEGClient(
        config=SovereignConfig(
            base_url="https://backend.sovereigneg.com/v1",
            primary_api_key="sk-primary",
            fallback_api_key="sk-fallback",
            max_transient_retries=0,
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    parsed, tel = client.complete_json([{"role": "user", "content": "hi"}])
    assert parsed == {"build_security": {"has_backlit_keyboard": True}}
    assert tel.model_used == "gpt-oss-120b"
    assert tel.model_attempts == ["claude-haiku-5.5", "gpt-oss-120b"]
    # Invalid model JSON is a model-output failure, not key exhaustion: must NOT retry fallback key on haiku
    assert calls == [
        ("Bearer sk-primary", "claude-haiku-5.5"),
        ("Bearer sk-primary", "gpt-oss-120b"),
    ]


def test_transient_503_retries_before_switching_without_exhausting_primary() -> None:
    attempts = {"primary": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer sk-primary":
            attempts["primary"] += 1
            if attempts["primary"] == 1:
                return httpx.Response(503, text="Upstream temporarily overloaded")
        return httpx.Response(200, json=_ok_body({"memory": {"speed": "5200 MHz"}}))

    client = SovereignEGClient(
        config=SovereignConfig(
            base_url="https://backend.sovereigneg.com/v1",
            primary_api_key="sk-primary",
            fallback_api_key="sk-fallback",
            max_transient_retries=1,
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client._backoff = (0.0, 0.0)

    parsed, tel = client.complete_json([{"role": "user", "content": "hi"}])
    assert parsed == {"memory": {"speed": "5200 MHz"}}
    assert attempts["primary"] == 2
    assert tel.primary_key_exhausted is False
    assert tel.key_slot_used == "primary"
