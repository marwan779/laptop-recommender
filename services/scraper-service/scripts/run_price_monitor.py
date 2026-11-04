"""CLI runner for testing the lightweight price monitor worker against real store offers."""

import argparse
import json
from pathlib import Path
import sys
import uuid

# Ensure service root is in path
SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.price_monitor.models import PriceCheckBatchRequest, PriceCheckItem  # noqa: E402
from app.price_monitor.service import PriceMonitorService  # noqa: E402


def load_offers_from_catalog(catalog_path: Path, store_key: str, limit: int = 10) -> list[PriceCheckItem]:
    """Load sample offers from the unified catalog for a specific store."""
    if not catalog_path.exists():
        print(f"Error: Catalog file not found at {catalog_path}")
        return []

    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    items: list[PriceCheckItem] = []
    store_k = store_key.lower().strip()

    for laptop in data.get("laptops", []):
        laptop_id = laptop.get("canonical_id", str(uuid.uuid4()))
        for offer in laptop.get("offers", []):
            if offer.get("store_key") == store_k and offer.get("product_url"):
                price = offer.get("price_egp")
                if price and price > 0:
                    items.append(
                        PriceCheckItem(
                            offer_id=str(uuid.uuid4()),
                            laptop_id=laptop_id,
                            product_url=offer["product_url"],
                            current_price_egp=float(price),
                            current_in_stock=bool(offer.get("in_stock", True)),
                        )
                    )
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break

    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Run lightweight price monitor on store offers")
    parser.add_argument(
        "--store",
        type=str,
        default="compumarts",
        choices=["compumarts", "elbadr", "sigma"],
        help="Store to monitor",
    )
    parser.add_argument("--limit", type=int, default=5, help="Number of offers to check")
    parser.add_argument("--concurrency", type=int, default=3, help="Max concurrent HTTP requests")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=SERVICE_ROOT / "scraping results" / "unified_catalog_latest.json",
        help="Path to catalog JSON",
    )
    args = parser.parse_args()

    print("\n=======================================================")
    print("  LIGHTWEIGHT PRICE MONITOR WORKER")
    print(f"  Store: {args.store.upper()} | Limit: {args.limit} | Concurrency: {args.concurrency}")
    print("=======================================================\n")

    items = load_offers_from_catalog(args.catalog, args.store, limit=args.limit)
    if not items:
        print(f"No valid offers found for store '{args.store}' in catalog.")
        return

    print(f"Loaded {len(items)} offers to check from {args.store}.")

    batch_request = PriceCheckBatchRequest(
        store_key=args.store,
        store_name=args.store.capitalize(),
        items=items,
    )

    monitor = PriceMonitorService(default_concurrency=args.concurrency, timeout_seconds=15.0)
    print("Dispatching asynchronous crawl...\n")

    response = monitor.check_batch(batch_request)

    print("-" * 90)
    print(f"{'STATUS':<15} | {'OLD PRICE':<12} | {'NEW PRICE':<12} | {'DELTA':<10} | {'URL'}")
    print("-" * 90)

    for r in response.results:
        old_p = f"{r.old_price_egp:,.0f} EGP"
        new_p = f"{r.new_price_egp:,.0f} EGP" if r.new_price_egp is not None else "N/A"
        delta = f"{r.price_delta_egp:+,.0f} EGP" if r.price_delta_egp != 0 else "0"
        url_short = r.product_url[:35] + "..." if len(r.product_url) > 35 else r.product_url

        status_tag = f"[{r.change_type.value}]"
        print(f"{status_tag:<15} | {old_p:<12} | {new_p:<12} | {delta:<10} | {url_short}")

    print("-" * 90)
    print(f"\nBatch Summary (Batch ID: {response.batch_id}):")
    print(f"  Total Checked : {response.total_items}")
    print(f"  Changed Offers: {response.changed_items_count}")
    print(f"  Price Drops   : {response.price_drops_count} (Drops)")
    print(f"  Price Hikes   : {response.price_hikes_count}")
    print(f"  Out of Stock  : {response.out_of_stock_count}")
    print(f"  Errors        : {response.errors_count}")
    print(f"  Duration      : {response.duration_seconds}s")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
