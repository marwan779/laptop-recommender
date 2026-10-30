"""CLI Runner to execute hardware metrics enrichment on scraping input catalog."""

import json
import sys
from pathlib import Path

# Add catalog-service root to path
service_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_root))

from app.services.catalog_metrics_service import CatalogMetricsService  # noqa: E402


def main() -> None:
    service = CatalogMetricsService()
    print("=" * 70)
    print("Starting Hardware Metrics Enrichment Pipeline...")
    print("=" * 70)

    summary = service.enrich_catalog(overwrite=True)

    print("\nExecution Summary:")
    print(json.dumps(summary, indent=2))
    print("\nPipeline executed successfully!")


if __name__ == "__main__":
    main()
