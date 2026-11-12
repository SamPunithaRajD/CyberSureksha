"""
DocuShield AI — Compliance & Audit Routes

Provides compliance officers and auditors with access to the immutable audit trails.
"""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, status
from loguru import logger

from app.database import get_collection
from app.utils.auth_deps import RoleChecker

router = APIRouter()


@router.get(
    "/logs",
    summary="Retrieve system audit logs (Auditors and Admins only)",
)
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200, description="Number of logs to retrieve"),
    skip: int = Query(0, ge=0, description="Number of logs to skip"),
    action_filter: str | None = Query(None, alias="action", description="Filter by action type"),
    current_user: dict = Depends(RoleChecker(["Compliance Auditor", "System Admin"]))
):
    """Retrieve paginated system audit logs, ordered from newest to oldest."""
    audit_col = get_collection("audit_logs")
    
    query = {}
    if action_filter:
        query["action"] = action_filter
        
    total = await audit_col.count_documents(query)
    
    cursor = (
        audit_col.find(query)
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    
    logs = []
    async for doc in cursor:
        logs.append({
            "id": str(doc["_id"]),
            "timestamp": doc["timestamp"].isoformat() if isinstance(doc.get("timestamp"), datetime) else doc.get("timestamp"),
            "user_id": doc.get("user_id"),
            "username": doc.get("username"),
            "role": doc.get("role"),
            "action": doc.get("action"),
            "details": doc.get("details", {})
        })
        
    return {
        "total": total,
        "logs": logs,
        "limit": limit,
        "skip": skip
    }
