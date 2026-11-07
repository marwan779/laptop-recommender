"""Unit tests for mapping catalog/event payloads to review targets."""

from app.domain.reviews.identity import ReviewIdentityExtractor
from app.services.reviews.mapper import target_from_mapping, targets_from_payload

SAMPLE_PAYLOAD = {
    "mpn": "90NB10N2M02TC0",
    "brand": "ASUS",
    "laptop_family": "Vivobook",
    "laptop_model": "Vivobook 16",
    "title": (
        'ASUS Vivobook 16 X1605VA-OACH007W \u2013 Intel Core i7-13620H, 16GB DDR4, '
        '512GB SSD, 16" FHD OLED 60Hz, 95% DCI-P3, Windows 11, Includes Mouse & Bag'
    ),
    "thumbnail_url": "https://www.compumarts.com/cdn/shop/files/ASUS-Vivobook-16.jpg",
    "specs": {
        "identity": {
            "brand": "ASUS",
            "laptop_family": "Vivobook",
            "laptop_model": "Vivobook 16",
            "manufacturer_part_number": "90NB10N2-M02TC0",
            "retailer_sku": "90NB10N2-M02TC0",
        }
    },
}


def test_maps_sample_catalog_payload():
    target = target_from_mapping(SAMPLE_PAYLOAD)

    assert target.laptop_id is None
    assert target.canonical_id is None
    assert target.brand == "ASUS"
    assert target.laptop_family == "Vivobook"
    assert target.laptop_model == "Vivobook 16"
    assert target.mpn == "90NB10N2M02TC0"
    assert target.manufacturer_part_number == "90NB10N2-M02TC0"
    assert target.retailer_sku == "90NB10N2-M02TC0"
    assert target.thumbnail_url == "https://www.compumarts.com/cdn/shop/files/ASUS-Vivobook-16.jpg"


def test_specs_identity_takes_precedence_over_top_level_fields():
    target = target_from_mapping(
        {
            "brand": "HP",
            "laptop_family": "Pavilion",
            "laptop_model": "Pavilion 15",
            "specs": {
                "identity": {
                    "brand": "ASUS",
                    "laptop_family": "Vivobook",
                    "laptop_model": "Vivobook 16",
                }
            },
        }
    )

    assert target.brand == "ASUS"
    assert target.laptop_family == "Vivobook"
    assert target.laptop_model == "Vivobook 16"


def test_maps_ids_urls_and_identity_lists():
    target = target_from_mapping(
        {
            "laptop_id": "lap-123",
            "canonical_id": "asus-vivobook-16-x1605va",
            "title": "ASUS Vivobook 16 Review",
            "skus": ["X1605VA-OACH007W", "X1605VA", "X1605VA"],
            "mpns": ["90NB10N2-M02TC0", ""],
            "product_urls": ["https://example.com/asus-vivobook-16"],
            "specs": {"identity": {"retailer_sku": "X1605VA-OACH007W"}},
        }
    )

    assert target.laptop_id == "lap-123"
    assert target.canonical_id == "asus-vivobook-16-x1605va"
    assert target.skus == ("X1605VA-OACH007W", "X1605VA")
    assert target.mpns == ("90NB10N2-M02TC0",)
    assert target.product_urls == ("https://example.com/asus-vivobook-16",)


def test_mapped_sample_feeds_identity_extractor():
    identity = ReviewIdentityExtractor().extract(target_from_mapping(SAMPLE_PAYLOAD))

    assert identity.brand == "ASUS"
    assert identity.full_sku == "X1605VA-OACH007W"
    assert identity.mpn == "90NB10N2-M02TC0"
    assert identity.mpn_compact == "90NB10N2M02TC0"


def test_targets_from_payload_maps_batch():
    targets = targets_from_payload(
        {
            "job_id": "job-1",
            "targets": [
                {"laptop_id": "lap-1", "title": "ASUS Vivobook 16 Review"},
                {"laptop_id": "lap-2", "title": "Lenovo LOQ 15 Review"},
            ],
        }
    )

    assert len(targets) == 2
    assert targets[0].laptop_id == "lap-1"
    assert targets[1].laptop_id == "lap-2"


def test_targets_from_payload_handles_missing_targets():
    assert targets_from_payload({"job_id": "job-1"}) == ()
