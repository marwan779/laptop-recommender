from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import engine

router = APIRouter()


@router.get("/health")
def health_check():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "ok",
    }