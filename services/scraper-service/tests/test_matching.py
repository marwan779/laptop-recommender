import pytest
from app.matching.engine import CommonMatchingEngine, MatchResult
from app.matching.normalizer import ModelNormalizer
from app.schemas.laptop import (
    ConfigurationItem,
    LaptopDetail,
    LaptopSummary,
    MatchMethod,
    MatchStatus,
    ModelFamily,
    RetailerProduct,
)
from app.scrapers.asus import AsusBrandScraper
from app.stores.base import BaseStoreScraper


# =============================================================================
# Helper Fixtures & Test Objects
# =============================================================================

@pytest.fixture
def family_s3407():
    config_aa = ConfigurationItem(
        model="S3407AA-SF117W",
        model_series="S3407AA",
        base_model="S3407",
        mpn=None,
        official_specs={"Processor": "Intel Core Ultra 5 226V", "Memory": "16GB LPDDR5X"},
        stores=[],
    )
    config_ca = ConfigurationItem(
        model="S3407CA-LY065W",
        model_series="S3407CA",
        base_model="S3407",
        mpn="90NB16J1-M00410",
        official_specs={"Processor": "Intel Core Ultra 7 256V", "Memory": "16GB LPDDR5X"},
        stores=[],
    )
    return ModelFamily(
        name="ASUS Vivobook S14 (S3407)",
        family="Vivobook",
        base_model="S3407",
        product_url="https://www.asus.com/eg-en/laptops/for-home/vivobook/asus-vivobook-s-14-s3407/",
        configurations=[config_aa, config_ca],
    )


@pytest.fixture
def family_s5452():
    config_ma = ConfigurationItem(
        model="S5452MA",
        model_series="S5452MA",
        base_model="S5452",
        mpn=None,
        official_specs={"Processor": "Intel Core Ultra 7 155H", "Memory": "16GB LPDDR5X"},
        stores=[],
    )
    return ModelFamily(
        name="ASUS Vivobook S14 (S5452)",
        family="Vivobook",
        base_model="S5452",
        product_url="https://www.asus.com/eg-en/laptops/for-home/vivobook/asus-vivobook-s-14-s5452/",
        configurations=[config_ma],
    )


@pytest.fixture
def family_proart_h7607():
    config_ba = ConfigurationItem(
        model="H7607BA",
        model_series="H7607BA",
        base_model="H7607",
        mpn=None,
        official_specs={"Processor": "AMD Ryzen AI 9 HX 370"},
        stores=[],
    )
    return ModelFamily(
        name="ASUS ProArt P16 (H7607)",
        family="ProArt",
        base_model="H7607",
        product_url="https://www.asus.com/eg-en/laptops/for-creators/proart/proart-p16-h7607/",
        configurations=[config_ba],
    )


# =============================================================================
# Unit Tests
# =============================================================================

def test_model_normalizer_tokens():
    """Verify regex token extraction for full SKUs, sub-models, and MPNs."""
    t1 = ModelNormalizer.extract_model_tokens("ASUS Vivobook S 14 S3407CA-LY065W Ultra 7")
    assert t1["full_sku"] == "S3407CA-LY065W"
    assert t1["sub_model"] == "S3407CA"
    assert t1["base_model"] == "S3407"

    t2 = ModelNormalizer.extract_model_tokens("ASUS ProArt P16 H7606WW-SE926W RTX 4070")
    assert t2["full_sku"] == "H7606WW-SE926W"
    assert t2["base_model"] == "H7606"

    t3 = ModelNormalizer.normalize_mpn("90NB16J1-M00410")
    assert t3 == "90NB16J1-M00410"


def test_case_1_hard_rejection_conflicting_base_model(family_s5452):
    """Case 1: S5452 target + S3407 candidate -> REJECTED."""
    target_config = family_s5452.configurations[0]  # S5452MA
    candidate = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="ASUS Vivobook S 14 S3407CA-LY065W Intel Core Ultra 7 256V",
        product_url="https://compumarts.com/products/asus-vivobook-s-14-s3407ca-ly065w",
        model_code="S3407CA-LY065W",
        base_model="S3407",
    )

    result = CommonMatchingEngine.evaluate(target_config, family_s5452, candidate)
    assert result.status == MatchStatus.REJECTED
    assert not result.is_accepted
    assert "Conflicting base model" in result.reason or "Conflicting model code" in result.reason


def test_case_2_exact_full_sku_match(family_s3407):
    """Case 2: Target S3407CA-LY065W + Candidate S3407CA-LY065W -> EXACT."""
    target_config = family_s3407.configurations[1]  # S3407CA-LY065W
    candidate = RetailerProduct(
        store_name="Sigma Computer",
        store_key="sigma",
        store_domain="sigma-computer.com",
        title="ASUS Vivobook S 14 OLED S3407CA-LY065W Ultra 7 256V 16GB 512GB SSD",
        product_url="https://www.sigma-computer.com/en/item?id=5600",
        model_code="S3407CA-LY065W",
        base_model="S3407",
    )

    result = CommonMatchingEngine.evaluate(target_config, family_s3407, candidate)
    assert result.status == MatchStatus.EXACT
    assert result.method == MatchMethod.FULL_SKU
    assert result.confidence >= 0.95
    assert result.is_accepted


def test_case_3_exact_mpn_match(family_s3407):
    """Case 3: Matching by Manufacturer Part Number (MPN) -> EXACT, confidence=1.0."""
    target_config = family_s3407.configurations[1]  # has mpn="90NB16J1-M00410"
    candidate = RetailerProduct(
        store_name="2B Egypt",
        store_key="twob",
        store_domain="2b.com.eg",
        title="Asus Vivobook S 14 S3407CA Intel Core Ultra 7 16GB RAM 512GB SSD",
        product_url="https://2b.com.eg/ar/asus-vivobook-s-14-s3407ca.html",
        mpn="90NB16J1-M00410",
        base_model="S3407",
    )

    result = CommonMatchingEngine.evaluate(target_config, family_s3407, candidate)
    assert result.status == MatchStatus.EXACT
    assert result.method == MatchMethod.MPN
    assert result.confidence == 1.0
    assert result.is_accepted


def test_case_4_hard_rejection_h7607_vs_h7606(family_proart_h7607):
    """Case 4: Target H7607 (ProArt P16) + Candidate H7606WW-SE926W -> REJECTED."""
    target_config = family_proart_h7607.configurations[0]  # H7607BA
    candidate = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="ASUS ProArt P16 OLED H7606WW-SE926W AMD Ryzen AI 9 HX 370 RTX 4070",
        product_url="https://compumarts.com/products/asus-proart-p16-h7606ww",
        model_code="H7606WW-SE926W",
        base_model="H7606",
    )

    result = CommonMatchingEngine.evaluate(target_config, family_proart_h7607, candidate)
    assert result.status == MatchStatus.REJECTED
    assert not result.is_accepted
    assert "H7607" in result.reason and "H7606" in result.reason


def test_case_5_generic_family_name_alone_is_unknown(family_s5452):
    """Case 5: Generic name without model or specs must return UNKNOWN and NOT be accepted."""
    target_config = family_s5452.configurations[0]
    candidate = RetailerProduct(
        store_name="Sigma Computer",
        store_key="sigma",
        store_domain="sigma-computer.com",
        title="ASUS Vivobook S14 Laptop Black",
        product_url="https://www.sigma-computer.com/en/item?id=9999",
        model_code=None,
        base_model=None,
    )

    result = CommonMatchingEngine.evaluate(target_config, family_s5452, candidate)
    assert result.status == MatchStatus.UNKNOWN
    assert result.confidence == 0.0
    assert not result.is_accepted


def test_case_6_candidate_deduplication():
    """Case 6: Multiple queries returning the same product must be deduplicated to 1 item."""
    c1 = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="ASUS Vivobook S 14 S3407CA-LY065W",
        product_url="https://compumarts.com/products/asus-vivobook-s3407?variant=123",
        retailer_product_id="PROD_1001",
    )
    c2 = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="ASUS Vivobook S 14 S3407CA-LY065W",
        product_url="https://compumarts.com/products/asus-vivobook-s3407?variant=456",
        retailer_product_id="PROD_1001",  # Same ID
    )
    c3 = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="ASUS Vivobook S 14 S3407CA-LY065W",
        product_url="https://compumarts.com/products/asus-vivobook-s3407",  # Same URL without params
        retailer_product_id="PROD_9999",
    )

    deduped = BaseStoreScraper.deduplicate_candidates([c1, c2, c3])
    assert len(deduped) == 1
    assert deduped[0].retailer_product_id == "PROD_1001"


def test_case_7_configuration_isolation(family_s3407):
    """Case 7: Candidate for S3407CA-LY065W must NOT attach to S3407AA-SF117W."""
    config_aa = family_s3407.configurations[0]  # S3407AA-SF117W
    config_ca = family_s3407.configurations[1]  # S3407CA-LY065W

    candidate_ca = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="ASUS Vivobook S 14 S3407CA-LY065W Ultra 7",
        product_url="https://compumarts.com/products/asus-s3407ca-ly065w",
        model_code="S3407CA-LY065W",
        base_model="S3407",
    )

    # Evaluate against config_aa -> REJECTED
    res_aa = CommonMatchingEngine.evaluate(config_aa, family_s3407, candidate_ca)
    assert res_aa.status == MatchStatus.REJECTED
    assert not res_aa.is_accepted

    # Evaluate against config_ca -> EXACT
    res_ca = CommonMatchingEngine.evaluate(config_ca, family_s3407, candidate_ca)
    assert res_ca.status == MatchStatus.EXACT
    assert res_ca.is_accepted


def test_case_8_asus_scraper_extract_configurations():
    """Case 8: AsusBrandScraper extracts distinct configurations from variants."""
    scraper = AsusBrandScraper(engine=None)  # Engine not needed for extract_configurations
    detail = LaptopDetail(
        brand="ASUS",
        name="ASUS Vivobook S 14 (S3407)",
        family="Vivobook",
        base_model="S3407",
        model="S3407AA-SF117W",
        model_variants=[
            "S3407AA-SF117W",
            "S3407CA-LY065W",
            "S3407AA",
            "S3407CA",
            "S3407",
        ],
        product_url="https://www.asus.com/eg-en/laptops/for-home/vivobook/asus-vivobook-s-14-s3407/",
        all_specs={"Processor": "Intel Core Ultra", "Memory": "16GB"},
    )

    configs = scraper.extract_configurations(detail)
    assert len(configs) == 2
    sku_names = [c.model for c in configs]
    assert "S3407AA-SF117W" in sku_names
    assert "S3407CA-LY065W" in sku_names
    assert all(c.base_model == "S3407" for c in configs)
    assert {c.model_series for c in configs} == {"S3407AA", "S3407CA"}


def test_case_9_base_model_with_aligned_cpu_specs():
    """Case 9: Base model matches with aligned processor specifications -> PROBABLE."""
    target_config = ConfigurationItem(
        model="S3407",
        model_series=None,
        base_model="S3407",
        mpn=None,
        official_specs={"Processor": "Intel Core Ultra 7 256V"},
        stores=[],
    )
    family = ModelFamily(
        name="ASUS Vivobook S14 (S3407)",
        base_model="S3407",
        product_url="https://asus.com/eg-en/s3407",
        configurations=[target_config],
    )
    candidate = RetailerProduct(
        store_name="Compumarts",
        store_key="compumarts",
        store_domain="compumarts.com",
        title="ASUS Vivobook S14 S3407 Intel Core Ultra 7 16GB 512GB",
        product_url="https://compumarts.com/products/s3407-ultra7",
        model_code="S3407",
        base_model="S3407",
    )

    result = CommonMatchingEngine.evaluate(target_config, family, candidate)
    assert result.status == MatchStatus.PROBABLE
    assert result.method == MatchMethod.BASE_MODEL_SPECS
    assert result.is_accepted


def test_case_10_store_aggregator_service_hierarchy():
    """Case 10: StoreAggregatorService end-to-end integration with mocked brand & store scrapers."""
    from unittest.mock import MagicMock
    from app.services.store_aggregator import StoreAggregatorService
    from app.scrapers.base import BaseBrandScraper
    from app.stores.base import BaseStoreScraper

    mock_engine = MagicMock()
    mock_brand = MagicMock(spec=BaseBrandScraper)
    mock_brand.brand_name = "ASUS"
    mock_brand.catalog_url = "https://www.asus.com/eg-en/laptops/"

    mock_summary = LaptopSummary(
        brand="ASUS",
        name="ASUS Vivobook S14 (S3407)",
        family="Vivobook",
        model="S3407",
        product_url="https://asus.com/s3407",
        specs_url="https://asus.com/s3407/techspec/",
    )
    mock_brand.get_laptop_summaries.return_value = [mock_summary]

    mock_detail = LaptopDetail(
        brand="ASUS",
        name="ASUS Vivobook S14 (S3407)",
        family="Vivobook",
        base_model="S3407",
        model="S3407AA-SF117W",
        model_variants=["S3407AA-SF117W", "S3407CA-LY065W"],
        product_url="https://asus.com/s3407",
        specs_url="https://asus.com/s3407/techspec/",
        all_specs={"Processor": "Intel Core Ultra 7"},
    )
    mock_brand.get_laptop_detail.return_value = mock_detail

    # extract_configurations returns two distinct configurations
    mock_brand.extract_configurations.return_value = [
        ConfigurationItem(
            model="S3407AA-SF117W",
            model_series="S3407AA",
            base_model="S3407",
            official_specs={"Processor": "Intel Core Ultra 5"},
            stores=[],
        ),
        ConfigurationItem(
            model="S3407CA-LY065W",
            model_series="S3407CA",
            base_model="S3407",
            mpn="90NB16J1-M00410",
            official_specs={"Processor": "Intel Core Ultra 7"},
            stores=[],
        ),
    ]

    mock_store_compumarts = MagicMock(spec=BaseStoreScraper)
    mock_store_compumarts.store_name = "Compumarts"
    mock_store_compumarts.store_key = "compumarts"
    mock_store_compumarts.store_domain = "compumarts.com"
    # Returns candidate for S3407AA-SF117W
    mock_store_compumarts.collect_store_candidates.return_value = [
        RetailerProduct(
            store_name="Compumarts",
            store_key="compumarts",
            store_domain="compumarts.com",
            title="ASUS Vivobook S 14 S3407AA-SF117W Core Ultra 5",
            product_url="https://compumarts.com/products/s3407aa-sf117w",
            model_code="S3407AA-SF117W",
            base_model="S3407",
            price_egp=42999.0,
            price_str="42,999.00 EGP",
        )
    ]

    mock_store_twob = MagicMock(spec=BaseStoreScraper)
    mock_store_twob.store_name = "2B Egypt"
    mock_store_twob.store_key = "twob"
    mock_store_twob.store_domain = "2b.com.eg"
    # Returns candidate for S3407CA-LY065W
    mock_store_twob.collect_store_candidates.return_value = [
        RetailerProduct(
            store_name="2B Egypt",
            store_key="twob",
            store_domain="2b.com.eg",
            title="Asus Vivobook S 14 S3407CA Intel Core Ultra 7",
            product_url="https://2b.com.eg/ar/s3407ca.html",
            mpn="90NB16J1-M00410",
            model_code="S3407CA",
            base_model="S3407",
            price_egp=54999.0,
            price_str="54,999.00 EGP",
        )
    ]

    aggregator = StoreAggregatorService(engine=mock_engine)
    # Monkey-patch get_all_store_scrapers to return our mocks
    from unittest.mock import patch
    with patch("app.services.store_aggregator.get_all_store_scrapers", return_value=[mock_store_compumarts, mock_store_twob]):
        catalog = aggregator.aggregate_brand_laptops(brand_scraper=mock_brand, laptop_limit=1)

    assert catalog.total_families == 1
    assert catalog.total_configurations == 2
    assert catalog.total_store_offers == 2

    family = catalog.model_families[0]
    config_aa = next(c for c in family.configurations if c.model == "S3407AA-SF117W")
    config_ca = next(c for c in family.configurations if c.model == "S3407CA-LY065W")

    # Verify strict isolation: AA gets Compumarts, CA gets 2B
    assert len(config_aa.stores) == 1
    assert config_aa.stores[0].store_key == "compumarts"
    assert config_aa.stores[0].match_status == MatchStatus.EXACT

    assert len(config_ca.stores) == 1
    assert config_ca.stores[0].store_key == "twob"
    assert config_ca.stores[0].match_status == MatchStatus.EXACT


def test_case_11_sub_model_partial_match_and_rejection(family_s3407):
    """Case 11: Candidate with sub-model 'S3407CA' matches S3407CA-LY065W (PROBABLE) and is REJECTED against S3407AA-SF117W."""
    config_aa = family_s3407.configurations[0]  # S3407AA-SF117W
    config_ca = family_s3407.configurations[1]  # S3407CA-LY065W

    candidate_sub = RetailerProduct(
        store_name="Sigma Computer",
        store_key="sigma",
        store_domain="sigma-computer.com",
        title="ASUS Vivobook S 14 OLED S3407CA Ultra 7 16GB",
        product_url="https://sigma-computer.com/en/item?id=8888",
        model_code="S3407CA",
        sub_model="S3407CA",
        base_model="S3407",
    )

    # Against AA: must be hard-rejected because S3407AA != S3407CA
    res_aa = CommonMatchingEngine.evaluate(config_aa, family_s3407, candidate_sub)
    assert res_aa.status == MatchStatus.REJECTED
    assert not res_aa.is_accepted

    # Against CA: sub-model series match without suffix -> PROBABLE
    res_ca = CommonMatchingEngine.evaluate(config_ca, family_s3407, candidate_sub)
    assert res_ca.status == MatchStatus.PROBABLE
    assert res_ca.method == MatchMethod.SUB_MODEL_SERIES
    assert res_ca.is_accepted
