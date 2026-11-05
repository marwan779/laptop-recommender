from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(request: Request, session: AsyncSession = Depends(get_db)):
    """Health check endpoint verifying API service, database, and broker connectivity."""
    try:
        result = await session.execute(text("SELECT 1"))
        db_status = "ok" if result.scalar() == 1 else "degraded"
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    broker = getattr(request.app.state, "broker", None)
    rabbitmq_connected = bool(broker and broker.is_connected)

    return {
        "status": "ok",
        "database": db_status,
        "rabbitmq_connected": rabbitmq_connected,
    }
