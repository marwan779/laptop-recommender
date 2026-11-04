import asyncio
from datetime import datetime, UTC
import time
from curl_cffi.requests import AsyncSession

from app.price_monitor.extractors import get_price_extractor
from app.price_monitor.models import (
    PriceChangeType,
    PriceCheckBatchRequest,
    PriceCheckBatchResponse,
    PriceCheckItem,
    PriceCheckItemResult,
)


class PriceMonitorService:
    """High-speed asynchronous price and stock monitoring service.

    Queries store product pages concurrently using curl_cffi with browser impersonation,
    extracts live price & availability, and classifies price changes.
    """

    def __init__(
        self,
        default_concurrency: int = 5,
        timeout_seconds: float = 15.0,
        request_delay_seconds: float = 0.2,
    ):
        self.default_concurrency = default_concurrency
        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = request_delay_seconds
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        }

    async def _check_single_item(
        self,
        session: AsyncSession,
        item: PriceCheckItem,
        extractor,
        semaphore: asyncio.Semaphore,
    ) -> PriceCheckItemResult:
        """Fetch and evaluate a single offer PDP with concurrency control."""
        async with semaphore:
            # Polite delay between requests
            if self.request_delay_seconds > 0:
                await asyncio.sleep(self.request_delay_seconds)

            start_time = datetime.now(UTC).isoformat()
            try:
                resp = await session.get(
                    item.product_url,
                    headers=self.headers,
                    impersonate="chrome120",
                    timeout=self.timeout_seconds,
                )
                http_status = resp.status_code

                # 1. Product removed / delisted
                if http_status in (404, 410):
                    has_changed = item.current_in_stock is not False
                    return PriceCheckItemResult(
                        offer_id=item.offer_id,
                        laptop_id=item.laptop_id,
                        product_url=item.product_url,
                        old_price_egp=item.current_price_egp,
                        new_price_egp=None,
                        old_in_stock=item.current_in_stock,
                        new_in_stock=False,
                        has_changed=has_changed,
                        change_type=PriceChangeType.OUT_OF_STOCK,
                        price_delta_egp=0.0,
                        http_status=http_status,
                        error_message="Product page not found (delisted)",
                        checked_at=start_time,
                    )

                if http_status != 200:
                    return PriceCheckItemResult(
                        offer_id=item.offer_id,
                        laptop_id=item.laptop_id,
                        product_url=item.product_url,
                        old_price_egp=item.current_price_egp,
                        new_price_egp=None,
                        old_in_stock=item.current_in_stock,
                        new_in_stock=item.current_in_stock,
                        has_changed=False,
                        change_type=PriceChangeType.ERROR,
                        price_delta_egp=0.0,
                        http_status=http_status,
                        error_message=f"HTTP status {http_status}",
                        checked_at=start_time,
                    )

                # 2. Extract price & stock via store extractor
                new_price, new_in_stock = extractor.extract_price_and_stock(resp.text, item.product_url)

                if new_price is None:
                    return PriceCheckItemResult(
                        offer_id=item.offer_id,
                        laptop_id=item.laptop_id,
                        product_url=item.product_url,
                        old_price_egp=item.current_price_egp,
                        new_price_egp=None,
                        old_in_stock=item.current_in_stock,
                        new_in_stock=new_in_stock,
                        has_changed=False,
                        change_type=PriceChangeType.ERROR,
                        price_delta_egp=0.0,
                        http_status=http_status,
                        error_message="Could not extract price from HTML",
                        checked_at=start_time,
                    )

                # 3. Classify price transition
                delta = round(new_price - item.current_price_egp, 2)
                has_price_change = abs(delta) >= 1.0  # Ignore negligible rounding discrepancies
                has_stock_change = new_in_stock != item.current_in_stock

                if has_price_change:
                    change_type = PriceChangeType.PRICE_DROP if delta < 0 else PriceChangeType.PRICE_HIKE
                    has_changed = True
                elif has_stock_change:
                    change_type = PriceChangeType.RESTOCKED if new_in_stock else PriceChangeType.OUT_OF_STOCK
                    has_changed = True
                else:
                    change_type = PriceChangeType.UNCHANGED
                    has_changed = False

                return PriceCheckItemResult(
                    offer_id=item.offer_id,
                    laptop_id=item.laptop_id,
                    product_url=item.product_url,
                    old_price_egp=item.current_price_egp,
                    new_price_egp=new_price,
                    old_in_stock=item.current_in_stock,
                    new_in_stock=new_in_stock,
                    has_changed=has_changed,
                    change_type=change_type,
                    price_delta_egp=delta,
                    http_status=http_status,
                    error_message=None,
                    checked_at=start_time,
                )

            except Exception as e:
                return PriceCheckItemResult(
                    offer_id=item.offer_id,
                    laptop_id=item.laptop_id,
                    product_url=item.product_url,
                    old_price_egp=item.current_price_egp,
                    new_price_egp=None,
                    old_in_stock=item.current_in_stock,
                    new_in_stock=item.current_in_stock,
                    has_changed=False,
                    change_type=PriceChangeType.ERROR,
                    price_delta_egp=0.0,
                    http_status=None,
                    error_message=str(e),
                    checked_at=start_time,
                )

    async def check_batch_async(
        self,
        batch_request: PriceCheckBatchRequest,
        concurrency: int | None = None,
    ) -> PriceCheckBatchResponse:
        """Asynchronously process a batch of offers for a specific store partition."""
        start_ts = time.time()
        started_at = datetime.now(UTC).isoformat()
        extractor = get_price_extractor(batch_request.store_key)
        sem = asyncio.Semaphore(concurrency or self.default_concurrency)

        async with AsyncSession() as session:
            tasks = [self._check_single_item(session, item, extractor, sem) for item in batch_request.items]
            results = await asyncio.gather(*tasks)

        completed_at = datetime.now(UTC).isoformat()
        duration = round(time.time() - start_ts, 2)

        # Count metrics
        changed_count = sum(1 for r in results if r.has_changed)
        drops_count = sum(1 for r in results if r.change_type == PriceChangeType.PRICE_DROP)
        hikes_count = sum(1 for r in results if r.change_type == PriceChangeType.PRICE_HIKE)
        oos_count = sum(1 for r in results if r.change_type == PriceChangeType.OUT_OF_STOCK)
        errors_count = sum(1 for r in results if r.change_type == PriceChangeType.ERROR)

        return PriceCheckBatchResponse(
            batch_id=batch_request.batch_id,
            store_key=batch_request.store_key,
            total_items=len(results),
            changed_items_count=changed_count,
            price_drops_count=drops_count,
            price_hikes_count=hikes_count,
            out_of_stock_count=oos_count,
            errors_count=errors_count,
            duration_seconds=duration,
            started_at=started_at,
            completed_at=completed_at,
            results=results,
        )

    def check_batch(
        self,
        batch_request: PriceCheckBatchRequest,
        concurrency: int | None = None,
    ) -> PriceCheckBatchResponse:
        """Synchronous convenience wrapper around check_batch_async."""
        return asyncio.run(self.check_batch_async(batch_request, concurrency=concurrency))
