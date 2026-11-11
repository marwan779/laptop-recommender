from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
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


# =============================================================================
# Multi-Store Price Tracking Over Time
# =============================================================================
#
# Each store offer defines a piecewise-constant step function of price:
#
#     P_i(t) = p_{i,k}   for t in [t_{i,k}, t_{i,k+1})
#
# History rows are only appended when a price or stock state actually changes.
# When serving a chart, the domain appends a synthetic "live edge" point so the
# curve extends to the most recent verification timestamp (today).
# =============================================================================


@dataclass(frozen=True)
class RawPriceEvent:
    """A single recorded price/stock observation for one store offer."""

    offer_id: str
    store_key: str
    price_egp: float
    in_stock: bool
    recorded_at: datetime


@dataclass(frozen=True)
class OfferCurrentState:
    """Live head state of a store offer, used for synthesis and the live edge."""

    offer_id: str
    store_key: str
    store_name: str
    product_url: str
    price_egp: float
    previous_price_egp: float | None
    in_stock: bool
    is_cheapest: bool
    created_at: datetime
    price_updated_at: datetime
    last_checked_at: datetime


@dataclass(frozen=True)
class PriceDataPoint:
    """One vertex of a store's price step function."""

    recorded_at: datetime
    price_egp: float
    in_stock: bool
    is_live_edge: bool = False


@dataclass(frozen=True)
class StorePriceSeries:
    """Complete plotted step series and statistics for one store offer."""

    offer_id: str
    store_key: str
    store_name: str
    product_url: str
    current_price_egp: float
    in_stock: bool
    is_cheapest: bool
    min_price_egp: float
    max_price_egp: float
    price_change_egp: float
    price_change_pct: float
    points: list[PriceDataPoint] = field(default_factory=list)


@dataclass(frozen=True)
class LaptopPriceHistoryCalculation:
    """Pure domain result describing every store curve for one canonical laptop."""

    laptop_id: str
    canonical_id: str
    lowest_ever_price_egp: float
    lowest_ever_store: str
    highest_ever_price_egp: float
    current_best_price_egp: float
    series: list[StorePriceSeries] = field(default_factory=list)


class PriceHistoryDomainService:
    """Pure domain service building multi-store price step functions.

    Completely isolated from SQLAlchemy, FastAPI, or network I/O.
    """

    #: Offers priced below this floor are scrape artifacts, not real listings.
    MIN_TRUSTWORTHY_PRICE_EGP: float = 5000.0

    @classmethod
    def build_laptop_price_history(
        cls,
        laptop_id: str,
        canonical_id: str,
        events: list[RawPriceEvent],
        offers: list[OfferCurrentState],
        days: int | None = None,
        now: datetime | None = None,
    ) -> LaptopPriceHistoryCalculation:
        """Build deduplicated, window-clipped, live-headed step series per store."""
        reference_now = now
        if reference_now is None:
            tzinfo = offers[0].last_checked_at.tzinfo if offers else None
            reference_now = datetime.now(tz=tzinfo)
        cutoff: datetime | None = None
        if days is not None and days > 0:
            cutoff = reference_now - timedelta(days=days)

        events_by_offer: dict[str, list[RawPriceEvent]] = {}
        for event in events:
            events_by_offer.setdefault(event.offer_id, []).append(event)

        series: list[StorePriceSeries] = []
        for offer in offers:
            raw_points = [
                event
                for event in sorted(
                    events_by_offer.get(offer.offer_id, []),
                    key=lambda e: e.recorded_at,
                )
                if cls._is_trustworthy_price(event.price_egp)
            ]

            # 1. Fallback synthesis when no history rows exist yet.
            if not raw_points:
                synthetic = cls._synthesize_baseline_points(offer)
                points = synthetic
            else:
                points = [
                    PriceDataPoint(
                        recorded_at=e.recorded_at,
                        price_egp=e.price_egp,
                        in_stock=e.in_stock,
                    )
                    for e in raw_points
                ]

            # 2. Deduplicate consecutive identical price/stock observations.
            points = cls._deduplicate(points)

            # 3. Clip to the requested window, anchoring the left edge.
            if cutoff is not None:
                points = cls._clip_to_window(points, cutoff, offer)

            # 4. Extend to the live verification timestamp.
            points = cls._append_live_edge(points, offer)

            series.append(cls._build_store_series(offer, points))

        return cls._aggregate(laptop_id, canonical_id, series)

    # -- construction helpers -------------------------------------------------

    @classmethod
    def _is_trustworthy_price(cls, price: float) -> bool:
        """Return True when a price looks like a real laptop listing."""
        return price >= cls.MIN_TRUSTWORTHY_PRICE_EGP

    @classmethod
    def _synthesize_baseline_points(cls, offer: OfferCurrentState) -> list[PriceDataPoint]:
        """Synthesize a minimal baseline curve for an offer with no history rows."""
        initial_price = offer.price_egp
        if offer.previous_price_egp and cls._is_trustworthy_price(offer.previous_price_egp):
            initial_price = offer.previous_price_egp

        points = [
            PriceDataPoint(
                recorded_at=offer.created_at,
                price_egp=initial_price,
                in_stock=offer.in_stock,
            )
        ]
        if offer.price_updated_at and offer.price_updated_at > offer.created_at:
            points.append(
                PriceDataPoint(
                    recorded_at=offer.price_updated_at,
                    price_egp=offer.price_egp,
                    in_stock=offer.in_stock,
                )
            )
        return points

    @staticmethod
    def _deduplicate(points: list[PriceDataPoint]) -> list[PriceDataPoint]:
        """Collapse consecutive points with identical price and stock state."""
        deduped: list[PriceDataPoint] = []
        for point in points:
            if not deduped:
                deduped.append(point)
                continue
            previous = deduped[-1]
            same_price = abs(previous.price_egp - point.price_egp) < 0.01
            if same_price and previous.in_stock == point.in_stock:
                continue
            deduped.append(point)
        return deduped

    @classmethod
    def _clip_to_window(
        cls,
        points: list[PriceDataPoint],
        cutoff: datetime,
        offer: OfferCurrentState,
    ) -> list[PriceDataPoint]:
        """Drop points before the cutoff and anchor a synthetic left-edge point."""
        if not points:
            return []

        after_cutoff = [p for p in points if p.recorded_at >= cutoff]
        if not after_cutoff:
            # The entire recorded curve predates the window: show the last known
            # price as a flat step from the cutoff to the live edge.
            last = points[-1]
            return [
                PriceDataPoint(
                    recorded_at=cutoff,
                    price_egp=last.price_egp,
                    in_stock=last.in_stock,
                )
            ]

        before_cutoff = [p for p in points if p.recorded_at < cutoff]
        if not before_cutoff:
            return after_cutoff

        anchor = before_cutoff[-1]
        return [
            PriceDataPoint(
                recorded_at=cutoff,
                price_egp=anchor.price_egp,
                in_stock=anchor.in_stock,
            ),
            *after_cutoff,
        ]

    @staticmethod
    def _append_live_edge(
        points: list[PriceDataPoint],
        offer: OfferCurrentState,
    ) -> list[PriceDataPoint]:
        """Extend the curve horizontally to the latest verification timestamp.

        When the offer's live head price is a scrape artifact, the curve simply
        continues the last trustworthy price instead of dropping to a bogus value.
        """
        live_at = offer.last_checked_at or offer.price_updated_at
        if live_at is None:
            return points

        live_price = (
            offer.price_egp
            if PriceHistoryDomainService._is_trustworthy_price(offer.price_egp)
            else (points[-1].price_egp if points else offer.price_egp)
        )

        if not points:
            return [
                PriceDataPoint(
                    recorded_at=live_at,
                    price_egp=live_price,
                    in_stock=offer.in_stock,
                    is_live_edge=True,
                )
            ]

        last = points[-1]
        if live_at <= last.recorded_at:
            return points

        return [
            *points,
            PriceDataPoint(
                recorded_at=live_at,
                price_egp=live_price,
                in_stock=offer.in_stock,
                is_live_edge=True,
            ),
        ]

    @staticmethod
    def _build_store_series(
        offer: OfferCurrentState,
        points: list[PriceDataPoint],
    ) -> StorePriceSeries:
        """Compute per-store extrema and deltas from its plotted step series."""
        prices = [p.price_egp for p in points] or [offer.price_egp]
        initial_price = prices[0]
        current_price = points[-1].price_egp if points else offer.price_egp
        change = round(current_price - initial_price, 2)
        change_pct = round((change / initial_price) * 100.0, 2) if initial_price else 0.0

        return StorePriceSeries(
            offer_id=offer.offer_id,
            store_key=offer.store_key,
            store_name=offer.store_name,
            product_url=offer.product_url,
            current_price_egp=round(current_price, 2),
            in_stock=offer.in_stock,
            is_cheapest=offer.is_cheapest,
            min_price_egp=round(min(prices), 2),
            max_price_egp=round(max(prices), 2),
            price_change_egp=change,
            price_change_pct=change_pct,
            points=points,
        )

    @staticmethod
    def _aggregate(
        laptop_id: str,
        canonical_id: str,
        series: list[StorePriceSeries],
    ) -> LaptopPriceHistoryCalculation:
        """Compute cross-store extrema and order cheapest in-stock offer first."""
        if not series:
            return LaptopPriceHistoryCalculation(
                laptop_id=laptop_id,
                canonical_id=canonical_id,
                lowest_ever_price_egp=0.0,
                lowest_ever_store="",
                highest_ever_price_egp=0.0,
                current_best_price_egp=0.0,
                series=[],
            )

        all_prices = [p.price_egp for s in series for p in s.points]
        lowest_store = min(series, key=lambda s: s.min_price_egp)
        current_best = min(
            (s.current_price_egp for s in series if s.in_stock),
            default=min(s.current_price_egp for s in series),
        )

        # Recompute the "cheapest" marker from the plotted series so a discarded
        # scrape-artifact offer can never claim the gold series colour.
        cheapest_series = min(
            (s for s in series if s.in_stock),
            key=lambda s: (s.current_price_egp, s.store_key),
            default=min(series, key=lambda s: (s.current_price_egp, s.store_key)),
        )
        series = [
            replace(s, is_cheapest=(s.store_key == cheapest_series.store_key))
            for s in series
        ]

        ordered = sorted(
            series,
            key=lambda s: (not s.in_stock, s.current_price_egp, s.store_key),
        )

        return LaptopPriceHistoryCalculation(
            laptop_id=laptop_id,
            canonical_id=canonical_id,
            lowest_ever_price_egp=round(min(all_prices), 2),
            lowest_ever_store=lowest_store.store_key,
            highest_ever_price_egp=round(max(all_prices), 2),
            current_best_price_egp=round(current_best, 2),
            series=ordered,
        )

