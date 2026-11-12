"""
Health Routes — Liveness and readiness probes for the DocuShield AI backend.
"""

from fastapi import APIRouter
from app.config import settings
from app.database import get_database

router = APIRouter()


@router.get("/")
async def health_check():
    """Basic liveness probe — confirms the service is running."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@router.get("/db")
async def db_health():
    """Readiness probe — verifies MongoDB connectivity."""
    try:
        db = get_database()
        await db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}
