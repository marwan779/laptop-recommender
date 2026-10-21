"""Unit tests verifying LLMAuditor Circuit Breaker and fast-fail behavior."""

from unittest.mock import MagicMock
import pytest

from pipeline.llm_auditor import LLMAuditor, LLMProviderEndpoint


def test_circuit_breaker_trips_after_consecutive_failures():
    """Verify circuit breaker trips and bypasses remote calls after max_consecutive_failures."""
    mock_ep = LLMProviderEndpoint(
        name="mock-groq",
        base_url="https://mock.groq.com",
        api_key_env="",
        model="mock-model",
        requests_per_minute=1000.0,
    )

    auditor = LLMAuditor(endpoints=[mock_ep], max_retries=1, max_consecutive_failures=2)
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("Server 500 error")
    auditor._clients["mock-groq"] = mock_client

    sample_laptop = {
        "title": "Test Laptop",
        "specs": {"memory": {"capacity_gb": 16}},
    }

    # Batch 1 fails
    res1 = auditor.audit_batch([sample_laptop])
    assert not res1.audited_laptops[0].corrections
    assert auditor.consecutive_failures == 1
    assert not auditor.is_circuit_broken
    assert mock_client.chat.completions.create.call_count == 1

    # Batch 2 fails -> trips circuit breaker
    res2 = auditor.audit_batch([sample_laptop])
    assert not res2.audited_laptops[0].corrections
    assert auditor.consecutive_failures == 2
    assert auditor.is_circuit_broken
    assert mock_client.chat.completions.create.call_count == 2

    # Batch 3 -> fast-path bypass! Client is NOT called
    res3 = auditor.audit_batch([sample_laptop])
    assert not res3.audited_laptops[0].corrections
    assert mock_client.chat.completions.create.call_count == 2  # Still 2, zero calls made!


def test_fatal_auth_error_permanently_blacklists_endpoint():
    """Verify HTTP 401 / invalid API key error immediately blacklists the endpoint."""
    mock_ep = LLMProviderEndpoint(
        name="mock-auth-fail",
        base_url="https://mock.groq.com",
        api_key_env="",
        model="mock-model",
        requests_per_minute=1000.0,
    )

    auditor = LLMAuditor(endpoints=[mock_ep], max_retries=3, max_consecutive_failures=1)
    mock_client = MagicMock()

    class MockHttpError(Exception):
        status_code = 401
        body = {"error": {"message": "Invalid API Key provided", "code": "invalid_api_key"}}

    mock_client.chat.completions.create.side_effect = MockHttpError()
    auditor._clients["mock-auth-fail"] = mock_client

    sample_laptop = {"title": "Test Laptop", "specs": {}}
    res = auditor.audit_batch([sample_laptop])

    assert "mock-auth-fail" in auditor._exhausted_endpoints
    assert auditor.is_circuit_broken
    assert mock_client.chat.completions.create.call_count == 1  # Blacklisted on first attempt, no retry!


def test_reset_circuit_breaker():
    """Verify circuit breaker can be manually reset."""
    mock_ep = LLMProviderEndpoint(
        name="mock-ep",
        base_url="https://mock.groq.com",
        api_key_env="",
        model="mock-model",
    )
    auditor = LLMAuditor(endpoints=[mock_ep])
    auditor.is_circuit_broken = True
    auditor.consecutive_failures = 5
    auditor._exhausted_endpoints.add("mock-ep")

    assert not auditor.is_available
    auditor.reset_circuit_breaker()

    assert not auditor.is_circuit_broken
    assert auditor.consecutive_failures == 0
    assert len(auditor._exhausted_endpoints) == 0
    assert auditor.is_available


def test_successful_audit_sets_is_audited_true_and_provider():
    """Verify successful audit sets is_audited=True and records provider metadata."""
    mock_ep = LLMProviderEndpoint(
        name="mock-provider",
        base_url="https://mock.groq.com",
        api_key_env="",
        model="mock-model",
    )
    auditor = LLMAuditor(endpoints=[mock_ep])
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content='{"audited_laptops": [{"laptop_id": "lap_0", "has_contradictions": false, "corrections": []}]}'))
    ]
    mock_client.chat.completions.create.return_value = mock_resp
    auditor._clients["mock-provider"] = mock_client

    sample_laptop = {"url": "https://compumarts.com/1", "title": "Test Laptop", "specs": {}}
    res = auditor.audit_batch([sample_laptop], identifiers=["lap_0"])

    assert res.provider == "mock-provider"
    assert res.status == "audited"
    assert len(res.audited_laptops) == 1
    assert res.audited_laptops[0].is_audited is True
    assert res.audited_laptops[0].status == "audited"


def test_catalog_pipeline_populates_audit_flag_and_metadata():
    """Verify GenericCatalogPipeline correctly sets is_audited and audit_meta on catalog records."""
    from app.schemas.laptop import RetailerProduct
    from pipeline.catalog_pipeline import GenericCatalogPipeline

    mock_ep = LLMProviderEndpoint(
        name="mock-pipeline-provider",
        base_url="https://mock.groq.com",
        api_key_env="",
        model="mock-model",
    )
    auditor = LLMAuditor(endpoints=[mock_ep])
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content='{"audited_laptops": [{"laptop_id": "https://compumarts.com/1", "has_contradictions": true, "corrections": [{"field_path": "display.refresh_rate_hz", "current_value": null, "corrected_value": 165, "reason": "test", "evidence_quote": "165Hz"}]}]}'))
    ]
    mock_client.chat.completions.create.return_value = mock_resp
    auditor._clients["mock-pipeline-provider"] = mock_client

    pipeline = GenericCatalogPipeline(ai_fallback=None, auditor=auditor, no_audit=False)

    p1 = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="Laptop 1",
        product_url="https://compumarts.com/1",
        specs={"Processor": "Intel Core i7-14650HX", "Memory": "16 GB DDR5"},
    )

    results = pipeline.process_catalog([p1])
    assert len(results) == 1
    item = results[0]

    assert item["is_audited"] is True
    assert item["audit_status"] == "audited"
    assert item["audit_meta"]["provider"] == "mock-pipeline-provider"
    assert item["audit_meta"]["has_contradictions"] is True
    assert item["audit_meta"]["corrections_count"] == 1


