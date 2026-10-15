from unittest.mock import MagicMock
import pytest

from gliner_extractor.token_budget import (
    GLINER_MAX_TOKENS,
    GLINER_SAFE_BUDGET,
    MAX_LABELS_PER_CALL,
    count_tokens,
    fit_to_budget,
)
from gliner_extractor.wrapper import GLiNERExtractor


def test_count_tokens_basic():
    text = "Intel Core Ultra 7 155H 16-Core Processor"
    labels = ["processor model", "cpu core count"]
    
    cnt = count_tokens(text, labels)
    assert isinstance(cnt, int)
    assert cnt > 0
    # Should include text tokens + labels tokens + special tokens
    assert cnt > len(text.split())


def test_fit_to_budget_dropping_priority():
    # Long title, long sibling facts, and a target row
    target_row = "Processor: Intel Core Ultra 9 275HX, 24 Cores / 24 Threads, 5.4 GHz Turbo"
    sibling_facts = [
        "RAM: 64GB DDR5 5600MHz Kingston Fury Impact",
        "Storage: 2TB Samsung 990 Pro PCIe 4.0 NVMe SSD",
        "Display: 16-inch QHD+ 240Hz 500nits DCI-P3 100% G-Sync",
    ]
    title = "Super Ultra Extreme Gaming Laptop 2026 Edition With Extra Words In Title To Exceed Any Normal Length"
    labels = ["processor model", "cpu core count", "clock speed"]

    # When budget is tight (e.g. 50 tokens), title should be dropped first
    result_tight = fit_to_budget(
        target_row=target_row,
        sibling_facts=sibling_facts,
        title=title,
        labels=labels,
        max_budget=50,
    )

    assert "Processor:" in result_tight  # Target row must NEVER be dropped
    tokens = count_tokens(result_tight, labels)
    assert tokens <= 50


def test_fit_to_budget_clause_cutting():
    # An extremely long target row that alone exceeds budget
    long_row = "Ports: HDMI 2.1 x1; USB-C Thunderbolt 4 x2; USB 3.2 Gen 2 Type-A x3; RJ-45 Gigabit Ethernet x1; Audio Jack 3.5mm x1; SD Card Reader Express 7.0 x1; Kensington Security Slot x1; DC-in Power Connector x1"
    labels = ["ports"]

    result = fit_to_budget(
        target_row=long_row,
        labels=labels,
        max_budget=35,
    )

    tokens = count_tokens(result, labels)
    assert tokens <= 35
    assert len(result) > 0


def test_gliner_wrapper_token_guard_and_label_chunking():
    extractor = GLiNERExtractor(lazy_load=True)
    extractor._ensure_loaded = MagicMock()
    mock_model = MagicMock()
    mock_model.predict_entities.return_value = [{"label": "ports", "text": "HDMI 2.1", "score": 0.9}]
    extractor._model = mock_model

    # 13 labels (exceeds MAX_LABELS_PER_CALL = 6)
    labels = [f"label_{i}" for i in range(13)]
    text = "Some long text about laptop specifications and hardware details"

    ents = extractor.extract_entities(text, labels)

    # predict_entities should have been called multiple times (chunked batches of <= 6)
    assert mock_model.predict_entities.call_count >= 3
    assert len(ents) > 0


def test_gliner_wrapper_spec_blocks_token_chunking():
    extractor = GLiNERExtractor(lazy_load=True)
    extractor._ensure_loaded = MagicMock()
    mock_model = MagicMock()
    mock_model.predict_entities.return_value = []
    extractor._model = mock_model

    specs = {f"Key_{i}": f"Value_{i} with long description to consume subword tokens quickly" for i in range(30)}
    title = "Test Laptop Model Title"
    labels = ["ram capacity", "storage capacity"]

    extractor.extract_from_spec_blocks(title, specs, labels, max_chunk_tokens=60)

    # Should have split into multiple chunks
    assert mock_model.predict_entities.call_count > 1

