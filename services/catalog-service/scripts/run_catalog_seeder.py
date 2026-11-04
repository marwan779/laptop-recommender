"""Standalone CLI runner for catalog ingestion and database seeding.

Fetches unified catalog from AWS S3 or a local JSON file, enriches it with
hardware metrics and TOPSIS inputs, resolves laptop identities, seeds PostgreSQL,
and updates store watermark checkpoints.

Usage:
    python scripts/run_catalog_seeder.py --file "scraping input/unified_catalog_latest.json"
    python scripts/run_catalog_seeder.py --s3-key "catalogs/unified_catalog_latest.json"
    python scripts/run_catalog_seeder.py  # Defaults to scraping input/unified_catalog_latest.json if present
"""

import argparse
import asyncio
from pathlib import Path
import sys

# Ensure catalog-service root is in sys.path
SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.common.logger import configure_logging, get_logger  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.catalog_ingestion_service import CatalogIngestionService, IngestionResult  # noqa: E402

configure_logging()
logger = get_logger("catalog.scripts.seeder")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest unified laptop catalog into PostgreSQL database.",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to local unified catalog JSON file",
    )
    parser.add_argument(
        "--s3-key",
        type=str,
        default=None,
        help="S3 object key for unified catalog JSON (e.g. 'catalogs/unified_catalog_latest.json')",
    )

    args = parser.parse_args()

    service = CatalogIngestionService()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            if args.s3_key:
                logger.info("Ingesting from S3 key: %s", args.s3_key)
                result: IngestionResult = await service.ingest_from_s3(
                    session=session,
                    s3_key=args.s3_key,
                    trigger_type="MANUAL_S3_CLI",
                )
            elif args.file:
                target_path = Path(args.file)
                if not target_path.exists() and (SERVICE_ROOT / args.file).exists():
                    target_path = SERVICE_ROOT / args.file
                target_path = target_path.resolve()
                logger.info("Ingesting from local file: %s", target_path)
                result = await service.ingest_from_file(
                    session=session,
                    file_path=target_path,
                    trigger_type="MANUAL_FILE_CLI",
                )
            else:
                default_file = SERVICE_ROOT / "scraping input" / "unified_catalog_latest.json"
                if default_file.exists():
                    logger.info("No source specified. Using default local file: %s", default_file)
                    result = await service.ingest_from_file(
                        session=session,
                        file_path=default_file,
                        trigger_type="DEFAULT_FILE_CLI",
                    )
                else:
                    default_s3_key = "catalogs/unified_catalog_latest.json"
                    logger.info("No local file found. Using default S3 key: %s", default_s3_key)
                    result = await service.ingest_from_s3(
                        session=session,
                        s3_key=default_s3_key,
                        trigger_type="DEFAULT_S3_CLI",
                    )

    print("\n" + "=" * 65)
    print("CATALOG INGESTION & SEEDER EXECUTION SUMMARY")
    print("=" * 65)
    print(f"Batch ID:         {result.batch_id}")
    print(f"Status:           {result.status}")
    print(f"Source:           {result.source}")
    print(f"Duration:         {result.duration_seconds:.2f}s")
    print(f"Laptops Total:    {result.total_laptops}")
    print(f"Laptops Created:  {result.new_laptops}")
    print(f"Laptops Updated:  {result.updated_laptops}")
    print(f"Offers Created:   {result.offers_created}")
    print(f"Offers Updated:   {result.offers_updated}")
    print(f"Metrics Created:  {result.metrics_created}")
    print(f"Metrics Updated:  {result.metrics_updated}")
    if result.error_message:
        print(f"Error:            {result.error_message}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
