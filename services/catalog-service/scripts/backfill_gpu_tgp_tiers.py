#!/usr/bin/env python3
"""Backfill script to recompute and update silicon_tier in laptop_metrics.

Evaluates each laptop's GPU against native reference limits in gpu_benchmarks.json
using the pure domain gpu_power_policy.
"""

import asyncio
from collections import Counter
import logging
from pathlib import Path
import sys

# Ensure services/catalog-service is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.domain.gpu_power_policy import evaluate_gpu_tgp
from app.models.laptop import LaptopConfiguration
from app.models.metrics import LaptopMetrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_gpu_tgp_tiers")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(LaptopConfiguration).options(selectinload(LaptopConfiguration.metrics))
        )
        laptops = result.scalars().all()

        total = len(laptops)
        logger.info("Found %d total laptops in database.", total)

        tier_counts: Counter[str] = Counter()
        updated_count = 0
        capped_examples = []

        for lap in laptops:
            if not lap.metrics:
                continue

            eval_res = evaluate_gpu_tgp(
                gpu_model=lap.gpu_model,
                integrated=bool(lap.gpu_integrated),
                actual_tdp_w=lap.gpu_tdp_w,
            )

            tier_counts[eval_res.tier] += 1

            if lap.metrics.silicon_tier != eval_res.tier:
                old_tier = lap.metrics.silicon_tier
                lap.metrics.silicon_tier = eval_res.tier
                updated_count += 1

            if "CAPPED" in eval_res.tier:
                capped_examples.append((
                    lap.canonical_id,
                    lap.brand,
                    lap.laptop_model,
                    lap.gpu_model,
                    lap.gpu_tdp_w,
                    eval_res.native_max_w,
                    eval_res.tier,
                ))

        await session.commit()
        logger.info("Successfully updated %d laptops in database.", updated_count)
        logger.info("Tier Distribution across %d laptops:", total)
        for tier, count in tier_counts.most_common():
            logger.info("  - %-25s: %3d laptops", tier, count)

        if capped_examples:
            logger.info("\nSample Capped GPUs identified:")
            for cid, brand, model, gpu_m, tdp, max_w, tier in capped_examples[:10]:
                logger.info(
                    "  [%s] %s %s - %s @ %sW (max %sW) -> %s",
                    cid, brand, model, gpu_m, tdp, max_w, tier
                )


if __name__ == "__main__":
    asyncio.run(main())
