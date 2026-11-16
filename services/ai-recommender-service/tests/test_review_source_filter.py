"""Regression tests for the S3/JSON review-source bouncer.

Every noisy fixture must disappear from both ``review_sources`` and
``deduplicated_chunks``/raw candidates, while genuine same-chassis and regional
reviews must survive both paths unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.domain.enrichment.chunking import _gather_raw_candidate_chunks
from app.domain.reviews.deduplication import audit_and_deduplicate_payload


def _identity(brand: str, family: str, model: str) -> Dict[str, Any]:
    return {"brand": brand, "laptop_family": family, "laptop_model": model}


def _item(
    identity: Dict[str, Any],
    *,
    editorial: Optional[List[Dict[str, Any]]] = None,
    discussions: Optional[List[Dict[str, Any]]] = None,
    videos: Optional[List[Dict[str, Any]]] = None,
    canonical_id: str = "cid-test",
    chassis_key: str = "test:chassis",
) -> Dict[str, Any]:
    return {
        "chassis_key": chassis_key,
        "primary_canonical_id": canonical_id,
        "matched_canonical_ids": [canonical_id],
        "identity": identity,
        "youtube": {"videos": videos or []},
        "communities": {
            "editorial": editorial or [],
            "discussions": discussions or [],
        },
        "nlp_review_profile": {},
    }


def _catalog(identity: Dict[str, Any], screen_size: Optional[float], canonical_id: str = "cid-test") -> Dict[str, Any]:
    return {
        "laptops": [
            {
                "canonical_id": canonical_id,
                "brand": identity.get("brand"),
                "laptop_family": identity.get("laptop_family"),
                "laptop_model": identity.get("laptop_model"),
                "specs": {"display": {"size_inches": screen_size}} if screen_size is not None else {},
            }
        ]
    }


def _audit(item: Dict[str, Any], identity: Dict[str, Any], screen_size: Optional[float]) -> Dict[str, Any]:
    output = audit_and_deduplicate_payload(
        reviews_data={"laptops": [item]},
        catalog_data=_catalog(identity, screen_size),
        include_unmatched_catalog=False,
    )
    return output["chassis_reviews"][0]


def _source_urls(review: Dict[str, Any]) -> set[str]:
    return {str(entry.get("url") or "") for entry in review.get("review_sources") or []}


def _chunk_text(review: Dict[str, Any]) -> str:
    return " || ".join(str(chunk.get("text") or "") for chunk in review.get("deduplicated_chunks") or []).lower()


def _discussion(title: str, url: str, body: str, *, platform: str = "level1techs", **extra: Any) -> Dict[str, Any]:
    return {
        "platform": platform,
        "post_title": title,
        "post_url": url,
        "post_body": body,
        **extra,
    }


def _video(title: str, url: str, transcript: str, *, channel: str = "Reviewer") -> Dict[str, Any]:
    return {
        "video_id": url.rsplit("=", 1)[-1],
        "title": title,
        "channel_name": channel,
        "video_url": url,
        "transcript_text": transcript,
        "transcript_source": "AUTO_CAPTIONS",
        "top_comments": [],
    }


_REJECTED_CASES: List[Dict[str, Any]] = [
    {
        "id": "level1techs-reply-url-244005-27",
        "identity": _identity("ASUS", "ProArt", "ProArt P16"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "ASUS ProArt P16 [RESOLVED] Spare workstation components",
            "https://forum.level1techs.com/t/asus-proart-p16/244005/27",
            "Spare workstation parts were tested with the ProArt P16 motherboard and desktop power supply.",
        ),
        "url": "https://forum.level1techs.com/t/asus-proart-p16/244005/27",
        "needle": "spare workstation parts were tested",
    },
    {
        "id": "level1techs-post-number-15",
        "identity": _identity("Lenovo", "LOQ", "LOQ 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "Lenovo LOQ 15 long-term owner notes",
            "https://forum.level1techs.com/t/lenovo-loq-15/195654/15",
            "A later reply measures the Lenovo LOQ 15 fan curve after the latest BIOS update.",
            post_number=15,
        ),
        "url": "https://forum.level1techs.com/t/lenovo-loq-15/195654/15",
        "needle": "a later reply measures",
    },
    {
        "id": "level1techs-tpm-bios-problem",
        "identity": _identity("Lenovo", "LOQ", "LOQ 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "Lenovo LOQ 15 TPM bios problem",
            "https://forum.level1techs.com/t/lenovo-loq-15/195700/1",
            "Lenovo LOQ 15 TPM bios problem persists after clearing the security chip.",
        ),
        "url": "https://forum.level1techs.com/t/lenovo-loq-15/195700/1",
        "needle": "tpm bios problem persists",
    },
    {
        "id": "level1techs-compatible-ram",
        "identity": _identity("Lenovo", "LOQ", "LOQ 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "Lenovo LOQ 15 Compatible ram?",
            "https://forum.level1techs.com/t/lenovo-loq-15/195701/1",
            "Compatible ram for the Lenovo LOQ 15 needs confirmation before purchase.",
        ),
        "url": "https://forum.level1techs.com/t/lenovo-loq-15/195701/1",
        "needle": "compatible ram for",
    },
    {
        "id": "level1techs-limit-charging",
        "identity": _identity("Lenovo", "LOQ", "LOQ 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "Lenovo LOQ 15 How to limit charging percentage",
            "https://forum.level1techs.com/t/lenovo-loq-15/195702/1",
            "How to limit charging percentage on the Lenovo LOQ 15 battery is unclear.",
        ),
        "url": "https://forum.level1techs.com/t/lenovo-loq-15/195702/1",
        "needle": "how to limit charging percentage",
    },
    {
        "id": "level1techs-buying-advice",
        "identity": _identity("Lenovo", "LOQ", "LOQ 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "Looking for new laptop to replace my old Lenovo",
            "https://forum.level1techs.com/t/lenovo-loq-15/195703/1",
            "Looking for new laptop advice and comparing the Lenovo LOQ 15 with other options.",
        ),
        "url": "https://forum.level1techs.com/t/lenovo-loq-15/195703/1",
        "needle": "looking for new laptop advice",
    },
    {
        "id": "level1techs-desktop-b550",
        "identity": _identity("ASUS", "ROG Strix", "G614PR"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "ASUS ROG Strix B550-F Gaming Motherboard Review",
            "https://forum.level1techs.com/t/asus-rog-strix-b550-f/195704/1",
            "The ASUS ROG Strix B550-F motherboard supports PCIe 4.0 and desktop Ryzen CPUs.",
        ),
        "url": "https://forum.level1techs.com/t/asus-rog-strix-b550-f/195704/1",
        "needle": "motherboard supports pcie",
    },
    {
        "id": "level1techs-desktop-z890",
        "identity": _identity("ASUS", "ProArt", "ProArt P16"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "ASUS ProArt Z890-Creator WiFi Motherboard Review",
            "https://forum.level1techs.com/t/asus-proart-z890/195705/1",
            "The ProArt Z890-Creator motherboard offers Thunderbolt and desktop CPU support.",
        ),
        "url": "https://forum.level1techs.com/t/asus-proart-z890/195705/1",
        "needle": "proart z890-creator motherboard",
    },
    {
        "id": "level1techs-hp255-cpu-collision",
        "identity": _identity("HP", "255", "HP 255 G10"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "HP Ultra 7 255H Laptop Review",
            "https://forum.level1techs.com/t/hp-255h/195706/1",
            "Intel Core Ultra 7 255H performance and efficiency were measured in this CPU test.",
        ),
        "url": "https://forum.level1techs.com/t/hp-255h/195706/1",
        "needle": "intel core ultra 7 255h performance",
    },
    {
        "id": "level1techs-garolite-g10",
        "identity": _identity("HP", "255R", "HP 255R G10"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "Garolite G10 vs FR4 for 3D printing",
            "https://forum.level1techs.com/t/garolite-g10/195707/1",
            "Garolite G10 is a tough 3D printing material compared with standard FR4 board.",
        ),
        "url": "https://forum.level1techs.com/t/garolite-g10/195707/1",
        "needle": "garolite g10 is a tough",
    },
    {
        "id": "arabhardware-news-isocell",
        "identity": _identity("HP", "255", "HP 255 G10"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "Samsung ISOCELL HP5 camera sensor announced",
            "https://arabhardware.net/news/samsung-isocell-hp5",
            "Samsung ISOCELL HP5 sensor news covers smartphone camera specifications.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/news/samsung-isocell-hp5",
        "needle": "samsung isocell hp5 sensor news",
    },
    {
        "id": "arabhardware-news-hpe",
        "identity": _identity("HP", "255", "HP 255 G10"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "HPE ProLiant server launch",
            "https://arabhardware.net/news/hpe-proliant",
            "HPE ProLiant server launch news covers enterprise rack hardware.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/news/hpe-proliant",
        "needle": "hpe proliant server launch",
    },
    {
        "id": "arabhardware-news-legion-go",
        "identity": _identity("Lenovo", "LOQ", "LOQ 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "Lenovo Legion Go 2 handheld launch",
            "https://arabhardware.net/news/legion-go-2",
            "Lenovo Legion Go 2 handheld launch news covers the new gaming console.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/news/legion-go-2",
        "needle": "legion go 2 handheld launch",
    },
    {
        "id": "arabhardware-news-teamgroup",
        "identity": _identity("ASUS", "TUF", "TUF A16"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "TEAMGROUP T-Force SSD review",
            "https://arabhardware.net/news/teamgroup-ssd",
            "TEAMGROUP T-Force SSD review covers storage speed and endurance.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/news/teamgroup-ssd",
        "needle": "teamgroup t-force ssd review",
    },
    {
        "id": "arabhardware-articles-ces",
        "identity": _identity("Lenovo", "LOQ", "LOQ 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "CES 2026 laptop announcements",
            "https://arabhardware.net/articles/ces-2026-laptops",
            "CES 2026 laptop announcements cover many upcoming notebooks and chips.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/articles/ces-2026-laptops",
        "needle": "ces 2026 laptop announcements",
    },
    {
        "id": "arabhardware-articles-expensive",
        "identity": _identity("ASUS", "TUF", "TUF A16"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "The most-expensive-laptop ever made",
            "https://arabhardware.net/articles/most-expensive-laptop",
            "The most-expensive-laptop article lists luxury materials and limited edition pricing.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/articles/most-expensive-laptop",
        "needle": "most-expensive-laptop article lists",
    },
    {
        "id": "arabhardware-videos-monitor",
        "identity": _identity("Acer", "Nitro V", "Nitro V 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "ACER NITRO XF272UP gaming monitor review",
            "https://arabhardware.net/videos/acer-nitro-xf272up",
            "ACER NITRO XF272UP gaming monitor review covers 27-inch 180Hz desktop display performance.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/videos/acer-nitro-xf272up",
        "needle": "acer nitro xf272up gaming monitor",
    },
    {
        "id": "arabhardware-review-scar18-on-g16",
        "identity": _identity("ASUS", "ROG Strix", "G614PR"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "مراجعة ASUS ROG Strix SCAR 18 G835LX",
            "https://arabhardware.net/reviews/asus-rog-strix-scar-18-g835lx",
            "This Scar 18 review measures thermals, fan noise, display brightness and gaming performance.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/reviews/asus-rog-strix-scar-18-g835lx",
        "needle": "this scar 18 review measures",
    },
    {
        "id": "arabhardware-review-tuf-a15-on-a16",
        "identity": _identity("ASUS", "TUF", "TUF A16 FA608PM"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "مراجعة ASUS TUF Gaming A15 FA506",
            "https://arabhardware.net/reviews/asus-tuf-gaming-a15-fa506",
            "This TUF A15 review covers thermals, keyboard, display and gaming endurance.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/reviews/asus-tuf-gaming-a15-fa506",
        "needle": "this tuf a15 review covers",
    },
    {
        "id": "arabhardware-review-zenbook-a16-on-14",
        "identity": _identity("ASUS", "Zenbook", "Zenbook 14"),
        "screen_size": 14.0,
        "kind": "discussion",
        "source": _discussion(
            "مراجعة لاب توب ASUS Zenbook A16",
            "https://arabhardware.net/reviews/asus-zenbook-a16",
            "This Zenbook A16 review covers thermals, OLED brightness, keyboard and battery life.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/reviews/asus-zenbook-a16",
        "needle": "this zenbook a16 review covers",
    },
    {
        "id": "arabhardware-review-vivobook-s15-on-16",
        "identity": _identity("ASUS", "Vivobook", "Vivobook 16"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "مراجعة لاب توب ASUS Vivobook S15",
            "https://arabhardware.net/reviews/asus-vivobook-s15",
            "This Vivobook S15 review covers thermals, OLED brightness, keyboard and battery life.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/reviews/asus-vivobook-s15",
        "needle": "this vivobook s15 review covers",
    },
    {
        "id": "laptopmag-victus16-on-15",
        "identity": _identity("HP", "Victus", "Victus 15"),
        "screen_size": 15.6,
        "kind": "editorial",
        "source": {
            "source": "LaptopMag",
            "review_url": "https://www.laptopmag.com/reviews/hp-victus-16-review",
            "verdict": "The Victus 16 delivers solid gaming performance and a bright display for the price.",
        },
        "url": "https://www.laptopmag.com/reviews/hp-victus-16-review",
        "needle": "victus 16 delivers solid",
    },
    {
        "id": "laptopmag-vivobook16-on-s14",
        "identity": _identity("ASUS", "Vivobook", "Vivobook S14"),
        "screen_size": 14.0,
        "kind": "editorial",
        "source": {
            "source": "LaptopMag",
            "review_url": "https://www.laptopmag.com/reviews/asus-vivobook-16-flip-review",
            "verdict": "The Vivobook 16 Flip is a flexible convertible with a bright touch display.",
        },
        "url": "https://www.laptopmag.com/reviews/asus-vivobook-16-flip-review",
        "needle": "vivobook 16 flip is a flexible",
    },
    {
        "id": "laptopmag-yoga-on-ideapad",
        "identity": _identity("Lenovo", "IdeaPad Slim", "IdeaPad Slim 3"),
        "screen_size": 15.6,
        "kind": "editorial",
        "source": {
            "source": "LaptopMag",
            "review_url": "https://www.laptopmag.com/reviews/lenovo-yoga-slim-9i-review",
            "verdict": "The Yoga Slim 9i is a premium ultrabook with an excellent OLED panel.",
        },
        "url": "https://www.laptopmag.com/reviews/lenovo-yoga-slim-9i-review",
        "needle": "yoga slim 9i is a premium",
    },
    {
        "id": "laptopmag-thinkbook-on-flex",
        "identity": _identity("Lenovo", "Flex", "Flex 5"),
        "screen_size": 15.6,
        "kind": "editorial",
        "source": {
            "source": "LaptopMag",
            "review_url": "https://www.laptopmag.com/reviews/lenovo-thinkbook-16-review",
            "verdict": "The ThinkBook 16 offers strong business features and a comfortable keyboard.",
        },
        "url": "https://www.laptopmag.com/reviews/lenovo-thinkbook-16-review",
        "needle": "thinkbook 16 offers strong",
    },
    {
        "id": "youtube-brand-only-in-channel",
        "identity": _identity("ASUS", "TUF", "TUF A16 FA608PM"),
        "screen_size": 16.0,
        "kind": "video",
        "source": _video(
            "RTX 5060 Gaming Laptop Review - Thermals & Performance",
            "https://www.youtube.com/watch?v=brand-only-channel",
            "This gaming laptop review measures thermals, fan noise, display brightness and gaming performance.",
            channel="ASUS TUF Gaming",
        ),
        "url": "https://www.youtube.com/watch?v=brand-only-channel",
        "needle": "this gaming laptop review measures",
    },
    {
        "id": "youtube-wrong-size-series",
        "identity": _identity("ASUS", "ROG Strix", "G614PR"),
        "screen_size": 16.0,
        "kind": "video",
        "source": _video(
            "ASUS ROG Strix SCAR 18 G835LX Review",
            "https://www.youtube.com/watch?v=wrong-size-series",
            "This Scar 18 review measures thermals, fan noise, display brightness and gaming performance.",
            channel="ASUS",
        ),
        "url": "https://www.youtube.com/watch?v=wrong-size-series",
        "needle": "this scar 18 review measures",
    },
]


@pytest.mark.parametrize("case", _REJECTED_CASES, ids=[case["id"] for case in _REJECTED_CASES])
def test_noisy_sources_are_removed_from_review_sources_and_chunks(case: Dict[str, Any]) -> None:
    item = _item(
        case["identity"],
        editorial=[case["source"]] if case["kind"] == "editorial" else [],
        discussions=[case["source"]] if case["kind"] == "discussion" else [],
        videos=[case["source"]] if case["kind"] == "video" else [],
    )

    review = _audit(item, case["identity"], case["screen_size"])
    assert case["url"] not in _source_urls(review)
    assert case["needle"] not in _chunk_text(review)

    candidates, _ = _gather_raw_candidate_chunks(item, screen_size=case["screen_size"])
    raw_text = " || ".join(str(candidate.get("text") or "") for candidate in candidates).lower()
    assert case["needle"] not in raw_text


_PRESERVED_CASES: List[Dict[str, Any]] = [
    {
        "id": "level1techs-proart-p16-notes",
        "identity": _identity("ASUS", "ProArt", "ProArt P16"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "Notes on the Asus ProArt P16 Testing (Windows)",
            "https://forum.level1techs.com/t/asus-proart-p16/123456/1",
            "Owner notes confirm the ProArt P16 display is bright and the fans stay quiet under load.",
        ),
        "url": "https://forum.level1techs.com/t/asus-proart-p16/123456/1",
        "needle": "owner notes confirm",
    },
    {
        "id": "arabhardware-lenovo-loq-rtx4050",
        "identity": _identity("Lenovo", "LOQ", "LOQ 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "مراجعة لاب توب الألعاب Lenovo LOQ بكارت RTX 4050",
            "https://arabhardware.net/reviews/lenovo-loq-rtx-4050",
            "Unique LOQ thermal evidence shows quiet fans and stable temperatures under sustained gaming load.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/reviews/lenovo-loq-rtx-4050",
        "needle": "unique loq thermal evidence",
    },
    {
        "id": "youtube-same-chassis-g614fr",
        "identity": _identity("ASUS", "ROG Strix", "G614PR"),
        "screen_size": 16.0,
        "kind": "video",
        "source": _video(
            "ASUS ROG Strix G16 G614FR Review - RTX 5070 Ti",
            "https://www.youtube.com/watch?v=same-chassis-g614fr",
            "Unique same chassis evidence shows the G614FR cooling stays quiet under gaming load.",
            channel="ASUS ROG",
        ),
        "url": "https://www.youtube.com/watch?v=same-chassis-g614fr",
        "needle": "unique same chassis evidence",
    },
    {
        "id": "arabhardware-acer-nitro-v15",
        "identity": _identity("Acer", "Nitro V", "Nitro V 15"),
        "screen_size": 15.6,
        "kind": "discussion",
        "source": _discussion(
            "مراجعة لاب توب Acer Nitro V15",
            "https://arabhardware.net/reviews/acer-nitro-v15",
            "Unique nitro evidence confirms the display is bright and the keyboard stays comfortable.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/reviews/acer-nitro-v15",
        "needle": "unique nitro evidence",
    },
    {
        "id": "arabhardware-zephyrus-g16",
        "identity": _identity("ASUS", "ROG Zephyrus", "ROG Zephyrus G16"),
        "screen_size": 16.0,
        "kind": "discussion",
        "source": _discussion(
            "مراجعة لاب توب ASUS ROG Zephyrus G16",
            "https://arabhardware.net/reviews/asus-rog-zephyrus-g16",
            "Unique zephyrus evidence confirms the OLED display is bright and the fans stay quiet.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/reviews/asus-rog-zephyrus-g16",
        "needle": "unique zephyrus evidence",
    },
    {
        "id": "arabhardware-zenbook-14-oled",
        "identity": _identity("ASUS", "Zenbook", "Zenbook 14"),
        "screen_size": 14.0,
        "kind": "discussion",
        "source": _discussion(
            "مراجعة لابتوب ASUS Zenbook 14 OLED",
            "https://arabhardware.net/reviews/asus-zenbook-14-oled",
            "Unique zenbook evidence confirms the OLED display is bright and the battery lasts all day.",
            platform="arabhardware",
        ),
        "url": "https://arabhardware.net/reviews/asus-zenbook-14-oled",
        "needle": "unique zenbook evidence",
    },
]


@pytest.mark.parametrize("case", _PRESERVED_CASES, ids=[case["id"] for case in _PRESERVED_CASES])
def test_genuine_sources_survive_review_sources_and_chunks(case: Dict[str, Any]) -> None:
    item = _item(
        case["identity"],
        editorial=[case["source"]] if case["kind"] == "editorial" else [],
        discussions=[case["source"]] if case["kind"] == "discussion" else [],
        videos=[case["source"]] if case["kind"] == "video" else [],
    )

    review = _audit(item, case["identity"], case["screen_size"])
    assert case["url"] in _source_urls(review)
    assert case["needle"] in _chunk_text(review)

    candidates, _ = _gather_raw_candidate_chunks(item, screen_size=case["screen_size"])
    raw_text = " || ".join(str(candidate.get("text") or "") for candidate in candidates).lower()
    assert case["needle"] in raw_text
