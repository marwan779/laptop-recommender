"""Unit tests for review identity extraction."""

from app.domain.reviews.identity import ReviewIdentityExtractor
from app.domain.reviews.models import ReviewTargetInput

SAMPLE_TITLE = (
    "ASUS Vivobook 16 X1605VA-OACH007W \u2013 Intel Core i7-13620H, 16GB DDR4, "
    '512GB SSD, 16" FHD OLED 60Hz, 95% DCI-P3, Windows 11, Includes Mouse & Bag'
)


def _sample_target() -> ReviewTargetInput:
    return ReviewTargetInput(
        title=SAMPLE_TITLE,
        brand="ASUS",
        laptop_family="Vivobook",
        laptop_model="Vivobook 16",
        mpn="90NB10N2M02TC0",
        manufacturer_part_number="90NB10N2-M02TC0",
        retailer_sku="90NB10N2-M02TC0",
        product_urls=("https://www.compumarts.com/products/asus-vivobook-16",),
        thumbnail_url="https://www.compumarts.com/cdn/shop/files/ASUS-Vivobook-16.jpg",
    )


def test_extracts_expected_identity_from_sample():
    identity = ReviewIdentityExtractor().extract(_sample_target())

    assert identity.brand == "ASUS"
    assert identity.family == "Vivobook"
    assert identity.model == "Vivobook 16"
    assert identity.full_sku == "X1605VA-OACH007W"
    assert identity.sub_model == "X1605VA"
    assert identity.base_model == "X1605"
    assert identity.mpn == "90NB10N2-M02TC0"
    assert identity.mpn_compact == "90NB10N2M02TC0"
    assert identity.cpu_hint == "i7-13620H"
    assert identity.title_core == "ASUS Vivobook 16 X1605VA-OACH007W"
    assert identity.language_hint == "en"
    assert identity.product_urls == ("https://www.compumarts.com/products/asus-vivobook-16",)
    assert identity.thumbnail_url == "https://www.compumarts.com/cdn/shop/files/ASUS-Vivobook-16.jpg"
    assert identity.warnings == ("missing_laptop_id",)


def test_mpn_variants_are_deduplicated():
    identity = ReviewIdentityExtractor().extract(_sample_target())

    assert identity.mpn_candidates == ("90NB10N2-M02TC0", "90NB10N2M02TC0")


def test_sku_candidates_include_full_sub_and_base_models():
    identity = ReviewIdentityExtractor().extract(_sample_target())

    assert identity.sku_candidates == ("X1605VA-OACH007W", "X1605VA", "X1605")


def test_title_only_input_derives_brand_family_and_model():
    identity = ReviewIdentityExtractor().extract(ReviewTargetInput(title=SAMPLE_TITLE))

    assert identity.brand == "ASUS"
    assert identity.family == "Vivobook"
    assert identity.model == "Vivobook 16"
    assert identity.full_sku == "X1605VA-OACH007W"
    assert identity.sub_model == "X1605VA"
    assert identity.base_model == "X1605"
    assert identity.mpn is None
    assert identity.target_key.startswith("derived:")
    assert "missing_laptop_id" in identity.warnings


def test_arabic_title_is_recognized_and_language_hint_is_arabic():
    identity = ReviewIdentityExtractor().extract(ReviewTargetInput(title="مراجعة لابتوب أسوس فيفوبوك 16 X1605VA"))

    assert identity.brand == "ASUS"
    assert identity.family == "Vivobook"
    assert identity.model == "Vivobook 16"
    assert identity.sub_model == "X1605VA"
    assert identity.language_hint == "ar"


def test_mixed_arabic_and_latin_title_is_arabic():
    identity = ReviewIdentityExtractor().extract(ReviewTargetInput(title="مراجعة ASUS Vivobook 16 X1605VA"))

    assert identity.brand == "ASUS"
    assert identity.family == "Vivobook"
    assert identity.model == "Vivobook 16"
    assert identity.language_hint == "ar"


def test_explicit_values_win_over_title_derivation():
    identity = ReviewIdentityExtractor().extract(
        ReviewTargetInput(
            title="ASUS Vivobook 16 X1605VA-OACH007W Review",
            brand="ASUS",
            laptop_family="Vivobook",
            laptop_model="Vivobook 16 Pro",
        )
    )

    assert identity.brand == "ASUS"
    assert identity.family == "Vivobook"
    assert identity.model == "Vivobook 16 Pro"


def test_compact_mpn_is_canonicalized():
    identity = ReviewIdentityExtractor().extract(
        ReviewTargetInput(title="ASUS Vivobook 16 Review", mpn="90NB10N2M02TC0")
    )

    assert identity.mpn == "90NB10N2-M02TC0"
    assert identity.mpn_compact == "90NB10N2M02TC0"


def test_retailer_sku_can_supply_model_code():
    identity = ReviewIdentityExtractor().extract(
        ReviewTargetInput(
            title="ASUS Vivobook 16 Review",
            retailer_sku="X1605VA-OACH007W",
        )
    )

    assert identity.full_sku == "X1605VA-OACH007W"
    assert identity.sub_model == "X1605VA"
    assert identity.mpn is None


def test_laptop_id_takes_precedence_for_target_key():
    identity = ReviewIdentityExtractor().extract(
        ReviewTargetInput(
            laptop_id="lap-123",
            canonical_id="asus-vivobook-16-x1605va",
            title=SAMPLE_TITLE,
        )
    )

    assert identity.target_key == "lap-123"


def test_empty_target_produces_warnings_instead_of_crashing():
    identity = ReviewIdentityExtractor().extract(ReviewTargetInput())

    assert identity.brand is None
    assert identity.family is None
    assert identity.model is None
    assert identity.target_key.startswith("derived:")
    assert set(identity.warnings) == {
        "missing_laptop_id",
        "missing_title",
        "missing_brand",
        "missing_model",
        "missing_exact_identifier",
    }


def test_brand_agnostic_sku_is_preserved():
    identity = ReviewIdentityExtractor().extract(
        ReviewTargetInput(
            title="Lenovo LOQ 15 Review",
            brand="Lenovo",
            laptop_family="LOQ",
            laptop_model="LOQ 15",
            skus=["83DV01HSED"],
            mpns=["83DV01HSED"],
        )
    )

    assert identity.sku_candidates == ("83DV01HSED",)
    assert identity.mpn == "83DV01HSED"
    assert "missing_exact_identifier" not in identity.warnings


def test_amd_cpu_hint_is_extracted():
    identity = ReviewIdentityExtractor().extract(ReviewTargetInput(title="Lenovo Legion 5 Ryzen 7 7840HS review"))

    assert identity.brand == "Lenovo"
    assert identity.family == "Legion"
    assert identity.cpu_hint == "Ryzen 7 7840HS"
