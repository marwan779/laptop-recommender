from dataclasses import dataclass, field
from enum import StrEnum


class PriceChangeType(StrEnum):
    UNCHANGED = "UNCHANGED"
    PRICE_DROP = "PRICE_DROP"
    PRICE_HIKE = "PRICE_HIKE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    RESTOCKED = "RESTOCKED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class OfferPriceTransition:
    """Pure domain event representing evaluated price and stock transition."""

    has_changed: bool
    change_type: PriceChangeType
    old_price: float
    new_price: float | None
    price_delta: float
    old_in_stock: bool
    new_in_stock: bool
    is_price_drop: bool
    is_price_hike: bool
    is_stock_change: bool


@dataclass(frozen=True)
class OfferSnapshot:
    """Pure domain snapshot of a store offer for calculation."""

    store_key: str
    price_egp: float
    in_stock: bool
    is_valid_price: bool = True


@dataclass(frozen=True)
class LaptopRollupCalculation:
    """Pure domain calculation result of aggregated laptop pricing across all stores."""

    min_price_egp: float
    max_price_egp: float
    price_spread_egp: float
    cheapest_store: str
    in_stock: bool
    available_stores: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValueScoreCalculation:
    """Pure domain calculation result for hardware value and deal tiering."""

    effective_price_egp: float
    composite_hw: float
    val_ratio: float
    value_score: float
    pricing_status: str


class PricingDomainService:
    """Pure domain service for pricing policies, rollups, and mathematical recalibrations.

    Completely isolated from SQLAlchemy, async I/O, or database connections.
    """

    MIN_REALISTIC_LAPTOP_PRICE: float = 5000.0
    SIGNIFICANT_PRICE_DELTA: float = 1.0

    @classmethod
    def evaluate_offer_transition(
        cls,
        current_price: float,
        new_price: float | None,
        current_stock: bool,
        new_stock: bool,
    ) -> OfferPriceTransition:
        """Evaluate price change and stock availability transition for a single offer."""
        if new_price is None:
            # If price could not be fetched or errored, no change to price
            return OfferPriceTransition(
                has_changed=False,
                change_type=PriceChangeType.UNCHANGED,
                old_price=current_price,
                new_price=None,
                price_delta=0.0,
                old_in_stock=current_stock,
                new_in_stock=current_stock,
                is_price_drop=False,
                is_price_hike=False,
                is_stock_change=False,
            )

        delta = round(new_price - current_price, 2)
        has_price_change = abs(delta) >= cls.SIGNIFICANT_PRICE_DELTA
        has_stock_change = current_stock != new_stock

        if has_price_change:
            is_drop = delta < 0
            change_type = PriceChangeType.PRICE_DROP if is_drop else PriceChangeType.PRICE_HIKE
            return OfferPriceTransition(
                has_changed=True,
                change_type=change_type,
                old_price=current_price,
                new_price=new_price,
                price_delta=delta,
                old_in_stock=current_stock,
                new_in_stock=new_stock,
                is_price_drop=is_drop,
                is_price_hike=not is_drop,
                is_stock_change=has_stock_change,
            )

        if has_stock_change:
            change_type = PriceChangeType.RESTOCKED if new_stock else PriceChangeType.OUT_OF_STOCK
            return OfferPriceTransition(
                has_changed=True,
                change_type=change_type,
                old_price=current_price,
                new_price=new_price,
                price_delta=delta,
                old_in_stock=current_stock,
                new_in_stock=new_stock,
                is_price_drop=False,
                is_price_hike=False,
                is_stock_change=True,
            )

        return OfferPriceTransition(
            has_changed=False,
            change_type=PriceChangeType.UNCHANGED,
            old_price=current_price,
            new_price=new_price,
            price_delta=0.0,
            old_in_stock=current_stock,
            new_in_stock=new_stock,
            is_price_drop=False,
            is_price_hike=False,
            is_stock_change=False,
        )

    @classmethod
    def calculate_laptop_rollup(
        cls,
        offers: list[OfferSnapshot],
    ) -> LaptopRollupCalculation | None:
        """Calculate canonical laptop price rollups, cheapest store, and stock across all offers."""
        if not offers:
            return None

        # Filter valid offers meeting realistic minimum threshold
        valid_offers = [o for o in offers if o.is_valid_price and o.price_egp >= cls.MIN_REALISTIC_LAPTOP_PRICE]
        if not valid_offers:
            valid_offers = offers  # Fallback to all offers if none pass threshold

        active_in_stock = [o for o in valid_offers if o.in_stock]

        if active_in_stock:
            cheapest = min(active_in_stock, key=lambda o: o.price_egp)
            new_min = cheapest.price_egp
            new_max = max(o.price_egp for o in active_in_stock)
            cheapest_store = cheapest.store_key
            is_in_stock = True
            available_stores = sorted(list({o.store_key for o in active_in_stock}))
        else:
            cheapest = min(valid_offers, key=lambda o: o.price_egp)
            new_min = cheapest.price_egp
            new_max = max(o.price_egp for o in valid_offers)
            cheapest_store = cheapest.store_key
            is_in_stock = False
            available_stores = []

        return LaptopRollupCalculation(
            min_price_egp=new_min,
            max_price_egp=new_max,
            price_spread_egp=round(new_max - new_min, 2),
            cheapest_store=cheapest_store,
            in_stock=is_in_stock,
            available_stores=available_stores,
        )

    @classmethod
    def recalculate_value_score(
        cls,
        min_price_egp: float,
        cpu_score: float,
        gpu_score: float,
        display_score: float,
        longevity_score: float,
        ram_capacity_gb: float = 16.0,
    ) -> ValueScoreCalculation:
        """Mathematically recalibrate the hardware capability value ratio and value score.

        Formula:
            composite_hw = 0.28*cpu + 0.32*gpu + 0.15*display + 0.10*ram_pts + 0.15*longevity
            val_ratio = (composite_hw ^ 1.35) / (min_price_egp / 10000)
            value_score = clamp(((val_ratio - 18.0) / (58.0 - 18.0)) * 100.0, 15.0, 100.0)
        """
        ram_pts = min(100.0, (float(ram_capacity_gb) / 32.0) * 100.0)
        composite_hw = (
            0.28 * float(cpu_score)
            + 0.32 * float(gpu_score)
            + 0.15 * float(display_score)
            + 0.10 * ram_pts
            + 0.15 * float(longevity_score)
        )

        effective_price = max(1.0, float(min_price_egp))
        val_ratio = round((composite_hw**1.35) / (effective_price / 10000.0), 2)
        raw_val_score = (val_ratio - 18.0) / (58.0 - 18.0) * 100.0
        clamped_score = round(max(15.0, min(100.0, raw_val_score)), 2)

        if clamped_score >= 75.0:
            pricing_status = "GREAT_DEAL"
        elif clamped_score >= 60.0:
            pricing_status = "GOOD_VALUE"
        elif clamped_score >= 45.0:
            pricing_status = "FAIR_VALUE"
        else:
            pricing_status = "POOR_VALUE"

        return ValueScoreCalculation(
            effective_price_egp=effective_price,
            composite_hw=round(composite_hw, 2),
            val_ratio=val_ratio,
            value_score=clamped_score,
            pricing_status=pricing_status,
        )
