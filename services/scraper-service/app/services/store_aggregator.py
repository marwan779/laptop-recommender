from typing import Sequence

from app.engine.base import IScraperEngine
from app.matching.engine import CommonMatchingEngine
from app.schemas.laptop import BrandStoreCatalog, ConfigurationItem, ModelFamily, RetailOffer
from app.scrapers.base import BaseBrandScraper
from app.stores.base import BaseStoreScraper
from app.stores.registry import get_all_store_scrapers, get_store_scraper


class StoreAggregatorService:
    """Orchestrates Phase 1 (Official Brand Catalog) and Phase 2 (Egyptian Stores Deep Search).

    Maintains strict product hierarchy:
      Brand -> ModelFamily -> ConfigurationItem (Exact SKU) -> RetailOffer
    """

    def __init__(self, engine: IScraperEngine):
        self.engine = engine

    def aggregate_brand_laptops(
        self,
        brand_scraper: BaseBrandScraper,
        laptop_limit: int | None = 5,
        store_keys: Sequence[str] | None = None,
        offers_per_store: int = 5,
    ) -> BrandStoreCatalog:
        """1. Fetch canonical laptops from official brand catalog (Level 1).

        2. For each laptop, perform Brand Level 2 crawl to discover official configurations and specs.
        3. For each family, search Egyptian stores with targeted candidate queries.
        4. Pass candidates to CommonMatchingEngine to attach offers strictly to their matching configuration.
        5. Return hierarchical BrandStoreCatalog.
        """
        print(f"\n[Aggregator] === Step 1: Fetching official {brand_scraper.brand_name} catalog (Level 1) ===")
        canonical_summaries = brand_scraper.get_laptop_summaries(limit=None)

        # Prepare store scrapers
        if store_keys:
            store_scrapers = [get_store_scraper(k, self.engine) for k in store_keys]
        else:
            store_scrapers = get_all_store_scrapers(self.engine)

        store_names = [s.store_name for s in store_scrapers]
        print(f"[Aggregator] Registered Egyptian Stores for search: {', '.join(store_names)}")

        print(f"\n[Aggregator] === Step 2 & 3: Official Specifications & Multi-Store Aggregation ===")
        model_families: list[ModelFamily] = []

        for idx, summary in enumerate(canonical_summaries, 1):
            print(f"\n[Aggregator] --- Processing Laptop candidate [{idx}]: '{summary.name}' ---")

            # Brand Level 2 Crawl: Extract full model name, sub-model SKUs, and official specs
            detail = brand_scraper.get_laptop_detail(summary)
            if detail is None:
                print(f"[Aggregator] Skipping '{summary.name}': Empty placeholder or no specs published.")
                continue

            # Extract distinct official configurations under this family
            configurations = brand_scraper.extract_configurations(detail)
            base_model = detail.base_model or summary.model

            family_obj = ModelFamily(
                name=summary.name,
                family=summary.family,
                base_model=base_model,
                product_url=summary.product_url,
                specs_url=summary.specs_url,
                thumbnail_url=summary.thumbnail_url,
                configurations=configurations,
            )

            print(
                f"[Aggregator] Family Resolved: '{family_obj.name}' (Base: {base_model}) | "
                f"{len(configurations)} official configuration(s): "
                f"{[c.model for c in configurations]}"
            )

            # Build targeted candidate search queries across all configurations in this family
            queries = BaseStoreScraper.build_candidate_queries(
                brand=brand_scraper.brand_name,
                family_name=family_obj.name,
                base_model=base_model,
                configurations=configurations,
            )
            print(f"[Aggregator] Generated candidate queries: {queries}")

            # Collect candidates across all registered stores
            for store in store_scrapers:
                try:
                    candidates = store.collect_store_candidates(queries=queries, max_candidates=15)
                    print(f"[Aggregator] Evaluating {len(candidates)} candidate(s) from {store.store_name}...")

                    for candidate in candidates:
                        best_result = None
                        best_config: ConfigurationItem | None = None

                        # Evaluate candidate against each configuration in the family
                        for config in configurations:
                            result = CommonMatchingEngine.evaluate(
                                target_config=config,
                                target_family=family_obj,
                                candidate=candidate,
                            )
                            if result.is_accepted:
                                if best_result is None or result.confidence > best_result.confidence:
                                    best_result = result
                                    best_config = config

                        if best_config is not None and best_result is not None:
                            # Avoid duplicate retailer offers under the same configuration
                            existing_urls = {o.product_url.rstrip("/") for o in best_config.stores}
                            clean_cand_url = candidate.product_url.rstrip("/")
                            if clean_cand_url not in existing_urls:
                                offer = RetailOffer(
                                    store_name=candidate.store_name,
                                    store_key=candidate.store_key,
                                    store_domain=candidate.store_domain,
                                    title=candidate.title,
                                    price_egp=candidate.price_egp,
                                    price_str=candidate.price_str,
                                    in_stock=candidate.in_stock,
                                    product_url=candidate.product_url,
                                    thumbnail_url=candidate.thumbnail_url,
                                    retailer_sku=candidate.retailer_sku,
                                    retailer_mpn=candidate.mpn,
                                    match_status=best_result.status,
                                    match_method=best_result.method,
                                    match_confidence=best_result.confidence,
                                    match_reason=best_result.reason,
                                    specs=candidate.specs,
                                    raw_description=candidate.raw_description,
                                    scraped_at=candidate.scraped_at,
                                )
                                best_config.stores.append(offer)
                                print(
                                    f"  [+] Attached offer '{offer.title[:45]}...' to "
                                    f"configuration '{best_config.model}' ({best_result.status.value})"
                                )

                except Exception as e:
                    print(f"  [!] Failed searching on {store.store_name}: {e}")

            model_families.append(family_obj)

            if laptop_limit and len(model_families) >= laptop_limit:
                print(f"[Aggregator] Reached target limit of {laptop_limit} laptop(s). Finishing aggregation.")
                break

        total_families = len(model_families)
        total_configurations = sum(len(f.configurations) for f in model_families)
        total_offers = sum(len(c.stores) for f in model_families for c in f.configurations)

        return BrandStoreCatalog(
            brand=brand_scraper.brand_name,
            official_catalog_url=brand_scraper.catalog_url,
            total_families=total_families,
            total_configurations=total_configurations,
            total_store_offers=total_offers,
            model_families=model_families,
        )
