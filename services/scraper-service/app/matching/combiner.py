"""Multi-Store Catalog Combiner & Deduplication Engine.

Performs linear-time O(M) entity resolution across multiple retailer
store outputs using an Inverted Multi-Index and Union-Find Disjoint Set.
Includes explicit guards against edge cases:
  - Conflicting display refresh rates (vetoed across cluster)
  - Store RAM/SSD upgrades under base factory MPNs (isolated into separate clusters)
  - GPU VRAM / silicon variants (isolated)
  - Multi-offer price priority (in-stock valid price prioritized)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.common.logger import get_logger
from app.common.resilience import ErrorCategory, resilient_boundary
from app.matching.disjoint_set import DisjointSet
from app.matching.fingerprint import (
    are_hardware_compatible,
    generate_hardware_fingerprint,
    normalize_mpn,
    slugify,
)
from app.matching.fusion import merge_specifications, pick_best_title
from app.matching.models import (
    CanonicalLaptop,
    StoreOffer,
    UnifiedCatalog,
    utcnow_str,
)

logger = get_logger("matching.combiner")


class CatalogCombiner:
    """Consolidates and deduplicates laptop catalogs across multiple retail stores."""

    def __init__(self, min_valid_price_egp: float = 1000.0) -> None:
        self.min_valid_price_egp = min_valid_price_egp

    @staticmethod
    def _can_union_clusters(
        ds: DisjointSet,
        raw_items: dict[str, dict[str, Any]],
        source_id: str,
        cand_id: str,
    ) -> bool:
        """Verify candidate cluster has zero hardware or display contradictions with source item."""
        cluster_members = ds.get_members(cand_id)
        source_item = raw_items[source_id]
        return all(are_hardware_compatible(source_item, raw_items[m]) for m in cluster_members if m in raw_items)

    def combine_files(self, file_paths: list[Path | str]) -> UnifiedCatalog:
        """Load multiple store catalog JSON files from disk and consolidate them."""
        catalogs: list[dict[str, Any]] = []
        for fp in file_paths:
            path = Path(fp)
            if not path.is_file():
                logger.warning("[CatalogCombiner] File not found: '%s', skipping.", path)
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    catalogs.append(data)
            except Exception as exc:
                logger.error("[CatalogCombiner] Failed to read catalog '%s': %s", path, exc)

        return self.combine_catalogs(catalogs)

    def combine_catalogs(self, catalogs: list[dict[str, Any]]) -> UnifiedCatalog:
        """Consolidate parsed store catalog dictionaries into a UnifiedCatalog."""
        products_by_store: dict[str, list[dict[str, Any]]] = {}

        for cat in catalogs:
            store_k = cat.get("store_key") or "unknown_store"
            # Structured products from level 2 pipeline
            prods = cat.get("structured_products") or []
            if not prods and "products" in cat:
                # Fallback to level 1 / raw products if structured_products empty
                prods = cat.get("products") or []

            products_by_store.setdefault(store_k, []).extend(prods)

        return self.combine_products(products_by_store)

    def combine_products(
        self,
        products_by_store: dict[str, list[dict[str, Any]]],
    ) -> UnifiedCatalog:
        """Core consolidation algorithm using Inverted Indexes and Union-Find."""
        t_start = utcnow_str()
        ds = DisjointSet()

        mpn_to_items: dict[str, list[str]] = {}
        fingerprint_to_items: dict[str, list[str]] = {}
        raw_items: dict[str, dict[str, Any]] = {}

        total_listings = 0
        stores_seen: set[str] = set()

        # Step 1: Linear Ingestion & Equivalence Indexing
        for store_key, prods in products_by_store.items():
            stores_seen.add(store_key)
            for idx, p in enumerate(prods):
                total_listings += 1
                item_id = f"{store_key}_{idx}"

                with resilient_boundary(
                    category=ErrorCategory.DOM_PARSING,
                    source_component="matching.combiner",
                    context={"store_key": store_key, "item_idx": idx, "url": p.get("url")},
                    suppress=True,
                ):
                    specs = p.get("specs") or {}
                    ident = specs.get("identity") or {}

                    raw_mpn = p.get("mpn") or ident.get("manufacturer_part_number") or p.get("retailer_sku")
                    clean_mpn = normalize_mpn(raw_mpn)

                    brand = ident.get("brand") or "Generic"
                    family = ident.get("laptop_family")
                    model = ident.get("laptop_model") or p.get("title") or "Laptop"

                    fp = generate_hardware_fingerprint(brand=brand, family=family, specs=specs)

                    mem = specs.get("memory") or {}
                    ram_gb = int(mem.get("capacity_gb") or 0)

                    storage = specs.get("storage") or {}
                    storage_gb = int(storage.get("capacity_gb") or 0)

                    gpu_info = specs.get("gpu") or {}
                    vram_gb = int(gpu_info.get("vram_gb") or 0)
                    gpu_model = gpu_info.get("model") or ""

                    disp = specs.get("display") or {}
                    refresh_hz = int(disp.get("refresh_rate_hz") or 0)

                    cpu_info = specs.get("cpu") or {}
                    cpu_model = cpu_info.get("model") or cpu_info.get("full_name") or ""

                    # Store parsed record
                    raw_items[item_id] = {
                        "store_key": store_key,
                        "store_name": p.get("store_name") or store_key.capitalize(),
                        "store_domain": p.get("store_domain"),
                        "product_url": p.get("url") or "",
                        "title": p.get("title") or "Unknown Laptop",
                        "price_egp": float(p.get("price_egp") or 0.0),
                        "price_str": p.get("price_str"),
                        "in_stock": bool(p.get("in_stock", True)),
                        "retailer_sku": p.get("retailer_sku"),
                        "mpn": clean_mpn,
                        "thumbnail_url": p.get("thumbnail_url"),
                        "scraped_at": p.get("scraped_at") or t_start,
                        "specs": specs,
                        "brand": brand,
                        "family": family,
                        "model": model,
                        "fingerprint": fp,
                        "ram_gb": ram_gb,
                        "storage_gb": storage_gb,
                        "vram_gb": vram_gb,
                        "refresh_hz": refresh_hz,
                        "cpu_model": cpu_model,
                        "gpu_model": gpu_model,
                    }

                    # Initialize item in DisjointSet
                    ds.find(item_id)

                    # Tier 1: Probe MPN Index with hardware compatibility guard
                    if clean_mpn:
                        for prev_id in mpn_to_items.get(clean_mpn, []):
                            if self._can_union_clusters(ds, raw_items, item_id, prev_id):
                                ds.union(item_id, prev_id)
                                break
                        mpn_to_items.setdefault(clean_mpn, []).append(item_id)

                    # Tier 2: Probe Hardware DNA Fingerprint Index with cluster compatibility veto
                    if fp:
                        for prev_id in fingerprint_to_items.get(fp, []):
                            if self._can_union_clusters(ds, raw_items, item_id, prev_id):
                                ds.union(item_id, prev_id)
                                break
                        fingerprint_to_items.setdefault(fp, []).append(item_id)

        # Step 2: Resolve Clusters
        clusters = ds.get_clusters()
        logger.info(
            "[CatalogCombiner] Ingested %d listings across %d stores. Clustered into %d unique laptops.",
            total_listings,
            len(stores_seen),
            len(clusters),
        )

        canonical_laptops: list[CanonicalLaptop] = []

        # Step 3: Canonical Fusion & Rollups
        for _cluster_id, member_ids in clusters.items():
            listings = [raw_items[mid] for mid in member_ids if mid in raw_items]
            if not listings:
                continue

            # Pick primary identity
            best_title = pick_best_title(listings)
            brand = listings[0]["brand"]
            family = next((l["family"] for l in listings if l.get("family")), None)
            model = next((l["model"] for l in listings if l.get("model")), listings[0]["model"])
            mpn = next((l["mpn"] for l in listings if l.get("mpn")), None)
            thumb = next((l["thumbnail_url"] for l in listings if l.get("thumbnail_url")), None)

            # Build Canonical ID slug
            slug_tokens = [slugify(brand), slugify(family or model)]
            if mpn:
                slug_tokens.append(slugify(mpn))
            else:
                slug_tokens.append(slugify(listings[0]["fingerprint"])[:40])
            canon_id = "laptop_" + "_".join(t for t in slug_tokens if t)

            # Non-destructive Spec Fusion
            fused_specs: dict[str, Any] = {}
            for l in listings:
                fused_specs = merge_specifications(fused_specs, l.get("specs") or {})

            # Build Offers list
            offers: list[StoreOffer] = []
            for l in listings:
                price = l["price_egp"]
                is_valid = price > self.min_valid_price_egp
                offers.append(
                    StoreOffer(
                        store_key=l["store_key"],
                        store_name=l["store_name"],
                        store_domain=l["store_domain"],
                        product_url=l["product_url"],
                        title=l["title"],
                        price_egp=price,
                        price_str=l["price_str"],
                        in_stock=l["in_stock"],
                        retailer_sku=l["retailer_sku"],
                        mpn=l["mpn"],
                        thumbnail_url=l["thumbnail_url"],
                        scraped_at=l["scraped_at"],
                        is_valid_price=is_valid,
                    )
                )

            # Sort offers: valid prices first, in-stock first, lowest price ascending
            offers.sort(key=lambda o: (not o.is_valid_price, not o.in_stock, o.price_egp))

            # Rollups: Multi-Offer Resolution per store (Edge Case C)
            available_stores = list(dict.fromkeys(o.store_key for o in offers))
            prices_by_store: dict[str, float] = {}

            for store in available_stores:
                store_offers = [o for o in offers if o.store_key == store and o.is_valid_price]
                if not store_offers:
                    any_store_offers = [o for o in offers if o.store_key == store]
                    prices_by_store[store] = any_store_offers[0].price_egp if any_store_offers else 0.0
                    continue

                # Prioritize valid in-stock offers
                in_stock_offers = [o for o in store_offers if o.in_stock]
                if in_stock_offers:
                    best_offer = min(in_stock_offers, key=lambda o: o.price_egp)
                else:
                    best_offer = min(store_offers, key=lambda o: o.price_egp)

                prices_by_store[store] = best_offer.price_egp

            # Overall min and max price across all stores
            valid_offers = [o for o in offers if o.is_valid_price]
            valid_in_stock = [o for o in valid_offers if o.in_stock]

            if valid_in_stock:
                cheapest_offer = min(valid_in_stock, key=lambda o: o.price_egp)
                min_price = cheapest_offer.price_egp
                cheapest_store = cheapest_offer.store_key
            elif valid_offers:
                cheapest_offer = min(valid_offers, key=lambda o: o.price_egp)
                min_price = cheapest_offer.price_egp
                cheapest_store = cheapest_offer.store_key
            else:
                min_price = None
                cheapest_store = None

            max_price = max((o.price_egp for o in valid_offers), default=None)
            price_spread = (max_price - min_price) if (min_price is not None and max_price is not None) else 0.0

            canonical_laptops.append(
                CanonicalLaptop(
                    canonical_id=canon_id,
                    mpn=mpn,
                    brand=brand,
                    laptop_family=family,
                    laptop_model=model,
                    title=best_title,
                    thumbnail_url=thumb,
                    specs=fused_specs,
                    available_stores=available_stores,
                    stores_count=len(available_stores),
                    min_price_egp=min_price,
                    max_price_egp=max_price,
                    cheapest_store=cheapest_store,
                    price_spread_egp=round(price_spread, 2),
                    prices_by_store=prices_by_store,
                    offers=offers,
                )
            )

        # Sort: Multi-store laptops first (highest value), then alphabetically
        canonical_laptops.sort(key=lambda c: (-c.stores_count, c.brand, c.laptop_model))

        # Metrics
        multi_store_count = sum(1 for c in canonical_laptops if c.stores_count > 1)
        overlap_pct = (multi_store_count / len(canonical_laptops) * 100.0) if canonical_laptops else 0.0

        catalog = UnifiedCatalog(
            stores_included=sorted(stores_seen),
            total_raw_listings=total_listings,
            total_unique_laptops=len(canonical_laptops),
            multi_store_laptops_count=multi_store_count,
            overlap_rate_pct=round(overlap_pct, 2),
            laptops=canonical_laptops,
        )

        logger.info(
            "[CatalogCombiner] Consolidation complete: %d raw -> %d unique laptops (%d multi-store, %.1f%% overlap).",
            total_listings,
            len(canonical_laptops),
            multi_store_count,
            overlap_pct,
        )
        return catalog
