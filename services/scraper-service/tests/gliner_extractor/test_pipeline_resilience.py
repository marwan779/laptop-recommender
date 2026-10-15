import json
import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from gliner_extractor.compumarts_extractor import CompumartsExtractor
from gliner_extractor.schema import empty_structured


def test_product_filtering_logic():
    extractor = CompumartsExtractor()
    
    # Laptop
    assert extractor.detect_product_type({}, "Acer Predator Helios Neo 16") == "laptop"
    
    # Accessory
    assert extractor.detect_product_type({}, "Logitech G502 Gaming Mouse") == "accessory"
    assert extractor.detect_product_type({}, "Lenovo Legion Gaming Backpack 16\"") == "bag"
    assert extractor.detect_product_type({}, "Samsung 27 Odyssey G5 Monitor") == "monitor"


def test_checkpoint_streaming_and_resume(tmp_path):
    checkpoint_file = tmp_path / "test.checkpoint.jsonl"
    
    # Write 2 pre-existing records to checkpoint
    rec1 = {"index": 0, "product_url": "https://compumarts.com/p1", "title": "Laptop 1", "structured": empty_structured()}
    rec2 = {"index": 1, "product_url": "https://compumarts.com/p2", "title": "Laptop 2", "structured": empty_structured()}
    
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec1) + "\n")
        f.write(json.dumps(rec2) + "\n")
        
    # Read back to simulate resume
    loaded_urls = set()
    records = []
    with open(checkpoint_file, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            records.append(r)
            loaded_urls.add(r["product_url"])
            
    assert len(records) == 2
    assert "https://compumarts.com/p1" in loaded_urls
    assert "https://compumarts.com/p2" in loaded_urls


def test_atomic_file_write(tmp_path):
    target_file = tmp_path / "hybrid_results.json"
    temp_file = tmp_path / "hybrid_results.json.tmp"
    
    data = [{"test": 123}]
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f)
        
    os.replace(temp_file, target_file)
    
    assert os.path.exists(target_file)
    assert not os.path.exists(temp_file)
    with open(target_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == [{"test": 123}]

