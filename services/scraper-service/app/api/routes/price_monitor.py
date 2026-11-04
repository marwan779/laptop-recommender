from fastapi import APIRouter, status

from app.common.logger import get_logger
from app.price_monitor.models import PriceCheckBatchRequest, PriceCheckBatchResponse
from app.price_monitor.service import PriceMonitorService

logger = get_logger("scraper.api.price_monitor")
router = APIRouter(prefix="/price-monitor", tags=["Price & Stock Monitor"])


@router.post(
    "/check",
    response_model=PriceCheckBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Check live price and stock availability for a batch of offer PDPs",
    description=(
        "Concurrently fetches product pages for a single retailer, extracts live price and stock, "
        "classifies price transitions (DROP, HIKE, OUT_OF_STOCK, UNCHANGED), and returns the results."
    ),
)
async def check_price_batch(
    request: PriceCheckBatchRequest,
) -> PriceCheckBatchResponse:
    """Evaluate live price & stock for a batch of PDP URLs."""
    logger.info(
        "Received price monitor batch [%s] for store '%s' with %d items",
        request.batch_id,
        request.store_key,
        len(request.items),
    )
    service = PriceMonitorService()
    return await service.check_batch_async(request)
