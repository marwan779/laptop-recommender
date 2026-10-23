"""Unit & Integration Tests for Multi-Store Catalog Consolidation & Deduplication.

Verifies:
  - MPN normalization and hardware DNA fingerprinting
  - DisjointSet (Union-Find) transitive cluster resolution
  - Hierarchical spec fusion (filling nulls, resolving conflicts)
  - CatalogCombiner single-pass clustering and offer rollups
  - Automatic multi-store consolidation hook in ScrapeOrchestrator
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from app.matching.combiner import CatalogCombiner
from app.matching.disjoint_set import DisjointSet
from app.matching.fingerprint import generate_hardware_fingerprint, normalize_mpn
from app.matching.fusion import merge_specifications, pick_best_title
from app.matching.models import CanonicalLaptop, StoreOffer, UnifiedCatalog
from app.schemas.laptop import StoreCatalogResult
from app.schemas.orchestrator import ScrapeRequest, ScrapeTargetResult
from app.services.orchestrator import ScrapeOrchestrator


def test_normalize_mpn():
    """Verify MPN cleaning strips country suffixes, dashes, and ignores noise."""
    assert normalize_mpn("83DV01HSED#ABV") == "83DV01HSED"
    assert normalize_mpn("83DV01HSED/MEA") == "83DV01HSED"
    assert normalize_mpn("90NR0MC1-M008A0") == "90NR0MC1M008A0"
    assert normalize_mpn("ANV15-52-78UM") == "ANV155278UM"
    assert normalize_mpn("none") is None
    assert normalize_mpn("N/A") is None
    assert normalize_mpn("LAPTOP-1234") is None
    assert normalize_mpn("123") is None  # Too short


def test_hardware_fingerprint_generation():
    """Verify deterministic silicon & chassis fingerprint generation."""
    specs1 = {
        "cpu": {"model": "Intel Core i7-13645HX"},
        "gpu": {"model": "NVIDIA GeForce RTX 4050"},
        "memory": {"capacity_gb": 16},
        "storage": {"capacity_gb": 512},
        "display": {"size_inches": 15.6, "refresh_rate_hz": 144},
    }
    specs2 = {
        "cpu": {"full_name": "Intel Core i7-13645HX"},
        "gpu": {"model": "GeForce RTX 4050"},
        "memory": {"capacity_gb": 16},
        "storage": {"capacity_gb": 512},
        "display": {"size_inches": 15.6, "refresh_rate_hz": 144},
    }
    specs_diff_gpu = {
        "cpu": {"model": "Intel Core i7-13645HX"},
        "gpu": {"model": "GeForce RTX 4060"},  # Different GPU!
        "memory": {"capacity_gb": 16},
        "storage": {"capacity_gb": 512},
        "display": {"size_inches": 15.6, "refresh_rate_hz": 144},
    }

    fp1 = generate_hardware_fingerprint("Lenovo", "LOQ", specs1)
    fp2 = generate_hardware_fingerprint("Lenovo", "LOQ", specs2)
    fp_diff = generate_hardware_fingerprint("Lenovo", "LOQ", specs_diff_gpu)

    assert fp1 == fp2  # Same silicon configuration matches
    assert fp1 != fp_diff  # Different GPU does not match


def test_disjoint_set_transitive_clustering():
    """Verify Union-Find groups items transitively with path compression."""
    ds = DisjointSet()

    # Store 1 and Store 2 match
    ds.union("compumarts_0", "elbadr_5")
    # Store 2 and Store 3 match
    ds.union("elbadr_5", "sigma_12")

    # Transitive property: compumarts_0 and sigma_12 must share root
    assert ds.find("compumarts_0") == ds.find("sigma_12")

    clusters = ds.get_clusters()
    root = ds.find("compumarts_0")
    assert set(clusters[root]) == {"compumarts_0", "elbadr_5", "sigma_12"}


def test_spec_fusion_rules():
    """Verify non-destructive specification merging and conflict resolution."""
    specs_a = {
        "identity": {"brand": "Lenovo", "laptop_model": "LOQ 15"},
        "power_battery": {"battery_capacity_wh": 60.0, "power_adapter_w": None},
        "audio_webcam": {"webcam_resolution": "HD Webcam"},
        "connectivity": {"ports": ["1x USB-C", "2x USB-A"]},
    }
    specs_b = {
        "identity": {"brand": "Lenovo", "laptop_model": "LOQ 15IRX9"},
        "power_battery": {"battery_capacity_wh": None, "power_adapter_w": 170.0},
        "audio_webcam": {"webcam_resolution": "1080p FHD with Privacy Shutter"},
        "connectivity": {"ports": ["2x USB-A", "1x HDMI 2.1"]},
    }

    fused = merge_specifications(specs_a, specs_b)

    # Null filled
    assert fused["power_battery"]["battery_capacity_wh"] == 60.0
    assert fused["power_battery"]["power_adapter_w"] == 170.0

    # More specific string wins
    assert fused["audio_webcam"]["webcam_resolution"] == "1080p FHD with Privacy Shutter"

    # Port list union without duplicates
    assert len(fused["connectivity"]["ports"]) == 3
    assert "1x HDMI 2.1" in fused["connectivity"]["ports"]


def test_catalog_combiner_exact_mpn_and_fingerprint_matching(tmp_path: Path):
    """Verify end-to-end combination across MPN matching, DNA matching, and pricing rollups."""
    # Store A: CompuMarts
    cat_a = {
        "store_key": "compumarts",
        "store_name": "CompuMarts",
        "store_domain": "compumarts.com",
        "structured_products": [
            {
                "title": "LENOVO LOQ 15IRX9 83DV01HSED Laptop i7 RTX 4050",
                "url": "https://compumarts.com/loq-15",
                "price_egp": 63155.0,
                "in_stock": True,
                "mpn": "83DV01HSED",
                "specs": {
                    "identity": {"brand": "Lenovo", "laptop_family": "LOQ", "laptop_model": "LOQ 15IRX9"},
                    "cpu": {"model": "i7-13645HX"},
                    "gpu": {"model": "RTX 4050"},
                    "memory": {"capacity_gb": 16},
                    "storage": {"capacity_gb": 512},
                    "display": {"size_inches": 15.6, "refresh_rate_hz": 144},
                    "power_battery": {"battery_capacity_wh": 60.0},
                },
            },
            {
                "title": "ASUS Zenbook 14 OLED",
                "url": "https://compumarts.com/zenbook-14",
                "price_egp": 45000.0,
                "in_stock": True,
                "mpn": "90NB1401",
                "specs": {
                    "identity": {"brand": "ASUS", "laptop_family": "Zenbook", "laptop_model": "Zenbook 14"},
                    "cpu": {"model": "Ultra 7 155H"},
                    "gpu": {"model": "Intel Arc"},
                    "memory": {"capacity_gb": 16},
                    "storage": {"capacity_gb": 1024},
                    "display": {"size_inches": 14.0, "refresh_rate_hz": 120},
                },
            },
        ],
    }

    # Store B: El Badr (Omitted MPN for LOQ, but identical DNA; placeholder 1.0 EGP)
    cat_b = {
        "store_key": "elbadr",
        "store_name": "El Badr Group",
        "store_domain": "elbadrgroupeg.store",
        "structured_products": [
            {
                "title": "Lenovo LOQ 15 Gaming Laptop Core i7 RTX 4050",
                "url": "https://elbadr.com/loq-15",
                "price_egp": 1.0,  # Placeholder price!
                "in_stock": False,
                "mpn": None,  # Missing MPN!
                "specs": {
                    "identity": {"brand": "Lenovo", "laptop_family": "LOQ", "laptop_model": "LOQ 15"},
                    "cpu": {"model": "i7-13645HX"},
                    "gpu": {"model": "RTX 4050"},
                    "memory": {"capacity_gb": 16},
                    "storage": {"capacity_gb": 512},
                    "display": {"size_inches": 15.6, "refresh_rate_hz": 144},
                    "audio_webcam": {"webcam_resolution": "1080p FHD with E-Shutter"},
                },
            }
        ],
    }

    # Store C: Sigma (Matching MPN with different price)
    cat_c = {
        "store_key": "sigma",
        "store_name": "Sigma Computer",
        "store_domain": "sigma-computer.com",
        "structured_products": [
            {
                "title": "LENOVO LOQ 83DV01HSED RTX 4050",
                "url": "https://sigma.com/loq-15",
                "price_egp": 66500.0,
                "in_stock": True,
                "mpn": "83DV01HSED",
                "specs": {
                    "identity": {"brand": "Lenovo", "laptop_family": "LOQ", "laptop_model": "83DV01HSED"},
                    "cpu": {"model": "i7-13645HX"},
                    "gpu": {"model": "RTX 4050"},
                    "memory": {"capacity_gb": 16},
                    "storage": {"capacity_gb": 512},
                    "display": {"size_inches": 15.6, "refresh_rate_hz": 144},
                },
            }
        ],
    }

    combiner = CatalogCombiner(min_valid_price_egp=1000.0)
    unified = combiner.combine_catalogs([cat_a, cat_b, cat_c])

    assert unified.total_raw_listings == 4
    assert unified.total_unique_laptops == 2  # LOQ (merged across 3 stores) + Zenbook (1 store)
    assert unified.multi_store_laptops_count == 1
    assert unified.overlap_rate_pct == 50.0

    # Inspect the merged Lenovo LOQ laptop
    loq = next(l for l in unified.laptops if l.brand == "Lenovo")
    assert loq.stores_count == 3
    assert set(loq.available_stores) == {"compumarts", "elbadr", "sigma"}
    assert loq.mpn == "83DV01HSED"

    # Price rollups: 1.0 EGP placeholder filtered out from min_price
    assert loq.min_price_egp == 63155.0
    assert loq.max_price_egp == 66500.0
    assert loq.cheapest_store == "compumarts"
    assert loq.price_spread_egp == 3345.0
    assert loq.prices_by_store["compumarts"] == 63155.0
    assert loq.prices_by_store["sigma"] == 66500.0

    # Spec fusion verified: CompuMarts battery + El Badr webcam
    assert loq.specs["power_battery"]["battery_capacity_wh"] == 60.0
    assert loq.specs["audio_webcam"]["webcam_resolution"] == "1080p FHD with E-Shutter"

    # Save to disk test
    out_file = tmp_path / "unified.json"
    unified.save_json(out_file)
    assert out_file.exists()


def test_orchestrator_automatic_consolidation_hook(tmp_path: Path):
    """Verify that ScrapeOrchestrator automatically triggers CatalogCombiner on multi-store scrapes."""
    orchestrator = ScrapeOrchestrator(engine=MagicMock())

    # Mock two completed store targets
    res1 = ScrapeTargetResult(
        target_type="store",
        target_key="compumarts",
        target_name="CompuMarts",
        level=2,
        items_scraped=1,
        store_result=StoreCatalogResult(
            store_name="CompuMarts",
            store_key="compumarts",
            store_domain="compumarts.com",
            structured_products=[
                {
                    "title": "Laptop A",
                    "price_egp": 30000.0,
                    "mpn": "MPN12345",
                    "specs": {"identity": {"brand": "Dell"}},
                }
            ],
        ),
    )
    res2 = ScrapeTargetResult(
        target_type="store",
        target_key="sigma",
        target_name="Sigma Computer",
        level=2,
        items_scraped=1,
        store_result=StoreCatalogResult(
            store_name="Sigma Computer",
            store_key="sigma",
            store_domain="sigma-computer.com",
            structured_products=[
                {
                    "title": "Laptop A - Sigma",
                    "price_egp": 29000.0,
                    "mpn": "MPN12345",
                    "specs": {"identity": {"brand": "Dell"}},
                }
            ],
        ),
    )

    req = ScrapeRequest(
        target_type="store",
        targets=["compumarts", "sigma"],
        level=2,
        output_dir=str(tmp_path),
        send_email=False,
    )

    # Patch _scrape_store to return our mock targets
    orchestrator._scrape_store = MagicMock(side_effect=[res1, res2])

    resp = orchestrator.execute(req)
    assert resp.total_targets == 2

    # Verify that unified_catalog_latest.json was automatically created by the orchestrator hook
    unified_file = tmp_path / "unified_catalog_latest.json"
    assert unified_file.exists()

    with open(unified_file, encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_raw_listings"] == 2
    assert data["total_unique_laptops"] == 1
    assert data["laptops"][0]["cheapest_store"] == "sigma"
    assert data["laptops"][0]["min_price_egp"] == 29000.0
