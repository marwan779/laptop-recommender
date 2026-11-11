from datetime import UTC, datetime, timedelta

from app.domain.pricing import (
    OfferCurrentState,
    PriceHistoryDomainService,
    RawPriceEvent,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def _offer(
    offer_id: str,
    store_key: str,
    price: float,
    *,
    days_ago: int = 90,
    last_checked_days_ago: int = 0,
    is_cheapest: bool = False,
    in_stock: bool = True,
    previous_price: float | None = None,
) -> OfferCurrentState:
    created = NOW - timedelta(days=days_ago)
    updated = NOW - timedelta(days=1)
    return OfferCurrentState(
        offer_id=offer_id,
        store_key=store_key,
        store_name=store_key.capitalize(),
        product_url=f"https://{store_key}.example/product",
        price_egp=price,
        previous_price_egp=previous_price,
        in_stock=in_stock,
        is_cheapest=is_cheapest,
        created_at=created,
        price_updated_at=updated,
        last_checked_at=NOW - timedelta(days=last_checked_days_ago),
    )


def _event(offer_id: str, store: str, price: float, days_ago: int) -> RawPriceEvent:
    return RawPriceEvent(
        offer_id=offer_id,
        store_key=store,
        price_egp=price,
        in_stock=True,
        recorded_at=NOW - timedelta(days=days_ago),
    )


def test_single_store_series_extends_to_live_edge():
    offers = [_offer("o1", "elbadr", 45000.0, is_cheapest=True)]
    events = [_event("o1", "elbadr", 48000.0, 60)]

    result = PriceHistoryDomainService.build_laptop_price_history(
        laptop_id="laptop-1",
        canonical_id="canon-1",
        events=events,
        offers=offers,
        now=NOW,
    )

    assert len(result.series) == 1
    series = result.series[0]
    assert series.points[-1].is_live_edge is True
    assert series.points[-1].price_egp == 45000.0
    assert series.points[-1].recorded_at == NOW
    assert result.current_best_price_egp == 45000.0
    assert result.lowest_ever_price_egp == 45000.0
    assert result.highest_ever_price_egp == 48000.0


def test_multiple_stores_sorted_cheapest_first():
    offers = [
        _offer("o1", "sigma", 50000.0),
        _offer("o2", "elbadr", 45000.0, is_cheapest=True),
        _offer("o3", "btech", 47000.0),
        _offer("o4", "compumarts", 52000.0),
    ]
    events = [
        _event("o1", "sigma", 50000.0, 40),
        _event("o2", "elbadr", 46000.0, 40),
        _event("o3", "btech", 47000.0, 40),
        _event("o4", "compumarts", 52000.0, 40),
    ]

    result = PriceHistoryDomainService.build_laptop_price_history(
        laptop_id="laptop-1",
        canonical_id="canon-1",
        events=events,
        offers=offers,
        now=NOW,
    )

    assert [s.store_key for s in result.series] == ["elbadr", "btech", "sigma", "compumarts"]
    assert result.lowest_ever_store == "elbadr"
    assert result.current_best_price_egp == 45000.0
    assert result.highest_ever_price_egp == 52000.0


def test_deduplicates_identical_consecutive_prices():
    offers = [_offer("o1", "elbadr", 45000.0)]
    events = [
        _event("o1", "elbadr", 45000.0, 50),
        _event("o1", "elbadr", 45000.0, 40),
        _event("o1", "elbadr", 45000.0, 30),
        _event("o1", "elbadr", 44000.0, 20),
        _event("o1", "elbadr", 44000.0, 10),
    ]

    result = PriceHistoryDomainService.build_laptop_price_history(
        laptop_id="laptop-1",
        canonical_id="canon-1",
        events=events,
        offers=offers,
        now=NOW,
    )

    points = result.series[0].points
    assert [(p.price_egp, p.is_live_edge) for p in points] == [
        (45000.0, False),
        (44000.0, False),
        (45000.0, True),
    ]


def test_window_clipping_anchors_left_edge():
    offers = [_offer("o1", "elbadr", 43000.0)]
    events = [
        _event("o1", "elbadr", 50000.0, 120),
        _event("o1", "elbadr", 47000.0, 100),
        _event("o1", "elbadr", 45000.0, 60),
        _event("o1", "elbadr", 43000.0, 10),
    ]

    result = PriceHistoryDomainService.build_laptop_price_history(
        laptop_id="laptop-1",
        canonical_id="canon-1",
        events=events,
        offers=offers,
        days=30,
        now=NOW,
    )

    points = result.series[0].points
    cutoff = NOW - timedelta(days=30)
    assert points[0].recorded_at == cutoff
    # Anchored at the last price recorded before the cutoff.
    assert points[0].price_egp == 45000.0
    assert all(p.recorded_at >= cutoff for p in points)
    assert points[-1].is_live_edge is True


def test_fallback_synthesis_when_no_history():
    offers = [
        _offer(
            "o1",
            "elbadr",
            45000.0,
            days_ago=30,
            previous_price=48000.0,
            is_cheapest=True,
        )
    ]

    result = PriceHistoryDomainService.build_laptop_price_history(
        laptop_id="laptop-1",
        canonical_id="canon-1",
        events=[],
        offers=offers,
        now=NOW,
    )

    points = result.series[0].points
    assert points[0].price_egp == 48000.0
    assert points[1].price_egp == 45000.0
    assert points[-1].is_live_edge is True
    assert result.lowest_ever_price_egp == 45000.0


def test_price_change_stats():
    offers = [_offer("o1", "elbadr", 42000.0)]
    events = [
        _event("o1", "elbadr", 50000.0, 40),
        _event("o1", "elbadr", 42000.0, 5),
    ]

    result = PriceHistoryDomainService.build_laptop_price_history(
        laptop_id="laptop-1",
        canonical_id="canon-1",
        events=events,
        offers=offers,
        now=NOW,
    )

    series = result.series[0]
    assert series.min_price_egp == 42000.0
    assert series.max_price_egp == 50000.0
    assert series.price_change_egp == -8000.0
    assert series.price_change_pct == -16.0


def test_empty_offers_returns_empty_calculation():
    result = PriceHistoryDomainService.build_laptop_price_history(
        laptop_id="laptop-1",
        canonical_id="canon-1",
        events=[],
        offers=[],
        now=NOW,
    )

    assert result.series == []
    assert result.current_best_price_egp == 0.0


def test_scrape_artifact_prices_are_excluded():
    """A 1 EGP scrape artifact must never become the best price or gold series."""
    offers = [
        _offer("o1", "elbadr", 66599.0, is_cheapest=True),
        _offer("o2", "compumarts", 72000.0),
    ]
    events = [
        _event("o1", "elbadr", 1.0, 20),
        _event("o2", "compumarts", 72000.0, 20),
    ]

    result = PriceHistoryDomainService.build_laptop_price_history(
        laptop_id="laptop-1",
        canonical_id="canon-1",
        events=events,
        offers=offers,
        now=NOW,
    )

    all_prices = [p.price_egp for s in result.series for p in s.points]
    assert min(all_prices) == 66599.0
    assert result.current_best_price_egp == 66599.0
    assert result.lowest_ever_price_egp == 66599.0
    cheapest = [s for s in result.series if s.is_cheapest]
    assert len(cheapest) == 1
    assert cheapest[0].store_key == "elbadr"
