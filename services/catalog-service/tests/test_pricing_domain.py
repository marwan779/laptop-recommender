from app.domain.pricing import (
    OfferSnapshot,
    PriceChangeType,
    PricingDomainService,
)


def test_evaluate_offer_transition_price_drop():
    transition = PricingDomainService.evaluate_offer_transition(
        current_price=50000.0,
        new_price=45000.0,
        current_stock=True,
        new_stock=True,
    )
    assert transition.has_changed is True
    assert transition.change_type == PriceChangeType.PRICE_DROP
    assert transition.price_delta == -5000.0
    assert transition.is_price_drop is True
    assert transition.is_price_hike is False
    assert transition.is_stock_change is False


def test_evaluate_offer_transition_price_hike():
    transition = PricingDomainService.evaluate_offer_transition(
        current_price=50000.0,
        new_price=53000.0,
        current_stock=True,
        new_stock=True,
    )
    assert transition.has_changed is True
    assert transition.change_type == PriceChangeType.PRICE_HIKE
    assert transition.price_delta == 3000.0
    assert transition.is_price_hike is True
    assert transition.is_price_drop is False


def test_evaluate_offer_transition_out_of_stock():
    transition = PricingDomainService.evaluate_offer_transition(
        current_price=50000.0,
        new_price=50000.0,
        current_stock=True,
        new_stock=False,
    )
    assert transition.has_changed is True
    assert transition.change_type == PriceChangeType.OUT_OF_STOCK
    assert transition.is_stock_change is True
    assert transition.new_in_stock is False


def test_evaluate_offer_transition_negligible_rounding():
    # Difference < 1.0 EGP is considered UNCHANGED
    transition = PricingDomainService.evaluate_offer_transition(
        current_price=50000.0,
        new_price=50000.5,
        current_stock=True,
        new_stock=True,
    )
    assert transition.has_changed is False
    assert transition.change_type == PriceChangeType.UNCHANGED


def test_calculate_laptop_rollup_picks_cheapest_in_stock():
    offers = [
        OfferSnapshot(store_key="compumarts", price_egp=55000.0, in_stock=True),
        OfferSnapshot(store_key="sigma", price_egp=52000.0, in_stock=True),
        OfferSnapshot(store_key="elbadr", price_egp=49000.0, in_stock=False),  # Cheaper, but OUT OF STOCK
    ]
    rollup = PricingDomainService.calculate_laptop_rollup(offers)
    assert rollup is not None
    assert rollup.min_price_egp == 52000.0
    assert rollup.cheapest_store == "sigma"
    assert rollup.in_stock is True
    assert rollup.max_price_egp == 55000.0
    assert rollup.price_spread_egp == 3000.0
    assert rollup.available_stores == ["compumarts", "sigma"]


def test_calculate_laptop_rollup_all_out_of_stock():
    offers = [
        OfferSnapshot(store_key="compumarts", price_egp=55000.0, in_stock=False),
        OfferSnapshot(store_key="sigma", price_egp=52000.0, in_stock=False),
    ]
    rollup = PricingDomainService.calculate_laptop_rollup(offers)
    assert rollup is not None
    assert rollup.min_price_egp == 52000.0
    assert rollup.in_stock is False
    assert rollup.available_stores == []


def test_calculate_laptop_rollup_empty_returns_none():
    assert PricingDomainService.calculate_laptop_rollup([]) is None


def test_recalculate_value_score_mathematics():
    calc = PricingDomainService.recalculate_value_score(
        min_price_egp=50000.0,
        cpu_score=85.0,
        gpu_score=85.0,
        display_score=80.0,
        longevity_score=80.0,
        ram_capacity_gb=32.0,
    )
    # Composite HW: 0.28*85 + 0.32*85 + 0.15*80 + 0.10*100 + 0.15*80 = 23.8 + 27.2 + 12 + 10 + 12 = 85.0
    assert calc.composite_hw == 85.0
    assert calc.value_score >= 15.0
    assert calc.value_score <= 100.0
    assert calc.pricing_status in ["GREAT_DEAL", "GOOD_VALUE", "FAIR_VALUE", "POOR_VALUE"]
