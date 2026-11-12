"""
API Router — Central router that mounts all route modules under their
respective prefixes and tags.
"""

from fastapi import APIRouter
from app.api.routes import documents, analysis, dashboard, health, auth, compliance, notifications, cases

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
api_router.include_router(cases.router, prefix="/cases", tags=["Cases"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["Compliance"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])


