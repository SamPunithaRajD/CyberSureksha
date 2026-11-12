"""
Dashboard Routes — Aggregated analytics for the DocuShield AI dashboard.
Provides summary statistics, recent activity, risk distribution, and
time-series fraud trends using MongoDB aggregation pipelines.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from loguru import logger

from app.database import get_collection
from app.utils.auth_deps import get_current_user, RoleChecker

router = APIRouter()


async def get_role_analysis_match(current_user: dict, active_only: bool = False) -> dict[str, Any]:
    """Helper to return MongoDB match filter for analyses based on user role and branch."""
    user_role = current_user.get("role")
    documents_col = get_collection("documents")
    doc_match = {"status": {"$ne": "deleted"}}
    
    if user_role == "Underwriting Officer":
        doc_match["uploaded_by"] = current_user.get("username")
        doc_ids = []
        cursor = documents_col.find(doc_match, {"_id": 1})
        async for doc in cursor:
            doc_ids.append(str(doc["_id"]))
        return {"document_id": {"$in": doc_ids}}
        
    elif user_role == "Branch Manager":
        doc_match["branch"] = current_user.get("branch", "Canara Bank")
        doc_ids = []
        cursor = documents_col.find(doc_match, {"_id": 1})
        async for doc in cursor:
            doc_ids.append(str(doc["_id"]))
        
        if active_only:
            # Managers only review escalated investigations in their active queue
            return {
                "document_id": {"$in": doc_ids},
                "workflow.status": "ESCALATED"
            }
        else:
            # Historical trends/summary include escalated and high-risk cases for their branch
            return {
                "document_id": {"$in": doc_ids},
                "$or": [
                    {"workflow.status": "ESCALATED"},
                    {"risk_score.tier": "high_risk"}
                ]
            }
        
    elif user_role == "Fraud Analyst":
        if active_only:
            # Analysts only see active investigations. APPROVED, REJECTED, SAFE_TO_PROCESS, CLOSED disappear.
            return {
                "workflow.status": {"$in": ["UNASSIGNED", "UNDER_REVIEW", "ESCALATED"]}
            }
        
    return {}



# ------------------------------------------------------------------ #
#  GET /summary — High-level dashboard summary
# ------------------------------------------------------------------ #
@router.get(
    "/summary",
    summary="Dashboard summary statistics",
)
async def dashboard_summary(
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """
    Count analyses by workflow status, calculate fraud rate and average
    processing time from the analyses collection.
    """
    analyses_col = get_collection("analyses")
    documents_col = get_collection("documents")

    # Enforce role-based branch/user isolation
    user_role = current_user.get("role")
    analysis_match = await get_role_analysis_match(current_user)

    # --- Group by workflow status and analysis status ---
    pipeline = [
        {"$match": analysis_match if analysis_match else {}},
        {"$group": {
            "_id": {
                "workflow_status": "$workflow.status",
                "analysis_status": "$status"
            },
            "count": {"$sum": 1}
        }}
    ]
    cursor = analyses_col.aggregate(pipeline)
    
    approved = 0
    blocked = 0
    flagged = 0
    processing = 0
    uploaded = 0
    failed = 0
    
    async for entry in cursor:
        w_status = entry["_id"].get("workflow_status", "UNASSIGNED")
        a_status = entry["_id"].get("analysis_status", "completed")
        count = entry["count"]
        
        if a_status == "failed":
            failed += count
        elif a_status in ("pending", "running"):
            processing += count
        else:
            if w_status == "APPROVED":
                approved += count
            elif w_status == "REJECTED":
                blocked += count
            elif w_status == "ESCALATED":
                flagged += count
            elif w_status == "UNDER_REVIEW":
                processing += count
            else: # UNASSIGNED
                flagged += count

    total_analyses = approved + blocked + flagged + processing + failed + uploaded

    # --- Fraud rate and breakdown ---
    tier_pipeline = [
        {"$match": analysis_match if analysis_match else {}},
        {"$group": {"_id": "$risk_score.tier", "count": {"$sum": 1}}}
    ]
    tier_cursor = analyses_col.aggregate(tier_pipeline)
    tier_counts = {}
    async for entry in tier_cursor:
        tier_counts[entry["_id"]] = entry["count"]
        
    high_risk_count = tier_counts.get("high_risk", 0)
    review_count = tier_counts.get("review", 0)
    low_risk_count = tier_counts.get("low_risk", 0)
    verified_count = tier_counts.get("verified", 0)

    fraud_rate = (
        round((high_risk_count / total_analyses) * 100, 2)
        if total_analyses > 0
        else 0.0
    )

    # --- Average processing time ---
    avg_time_match = {"processing_time_ms": {"$gt": 0}}
    if analysis_match:
        avg_time_match.update(analysis_match)
    avg_time_pipeline = [
        {"$match": avg_time_match},
        {"$group": {"_id": None, "avg_ms": {"$avg": "$processing_time_ms"}}},
    ]
    avg_cursor = analyses_col.aggregate(avg_time_pipeline)
    avg_processing_ms = 0.0
    async for entry in avg_cursor:
        avg_processing_ms = round(entry.get("avg_ms", 0), 2)

    logger.debug(f"Dashboard summary — {total_analyses} analyses, fraud rate {fraud_rate}% for role {user_role}")

    return {
        "total_documents": total_analyses,
        "status_breakdown": {
            "analyzed": total_analyses - processing - failed,
            "flagged": flagged,
            "blocked": blocked,
            "approved": approved,
            "uploaded": uploaded,
            "processing": processing,
            "failed": failed,
        },
        "tier_breakdown": {
            "verified": verified_count,
            "safe_to_process": low_risk_count,
            "review_queue": review_count,
            "rejected": high_risk_count
        },
        "total_analyses": total_analyses,
        "high_risk_count": high_risk_count,
        "fraud_rate_percent": fraud_rate,
        "avg_processing_time_ms": avg_processing_ms,
    }


# ------------------------------------------------------------------ #
#  GET /recent-activity — Last N analyses
# ------------------------------------------------------------------ #
@router.get(
    "/recent-activity",
    summary="Recent analysis activity",
)
async def recent_activity(
    limit: int = Query(10, ge=1, le=50, description="Number of recent items"),
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Return the most recent analyses with basic info, scoped by role."""
    analyses_col = get_collection("analyses")
    documents_col = get_collection("documents")

    analysis_match = await get_role_analysis_match(current_user, active_only=True)

    cursor = (
        analyses_col.find(analysis_match)
        .sort("created_at", -1)
        .limit(limit)
    )

    items: list[dict] = []
    async for analysis in cursor:
        doc_id = analysis.get("document_id", "")
        results = analysis.get("results", {})
        risk = analysis.get("risk_score", {})
        workflow = analysis.get("workflow", {})

        # Fetch document name
        doc_name = "Unknown"
        doc_branch = "Unknown"
        doc_uploaded_by = "Unknown"
        if doc_id:
            try:
                from bson import ObjectId
                doc = await documents_col.find_one({"_id": ObjectId(doc_id)})
                if doc:
                    doc_name = doc.get("original_filename", "Unknown")
                    doc_branch = doc.get("branch", "Canara Bank")
                    doc_uploaded_by = doc.get("uploaded_by", "system")
            except Exception:
                pass

        items.append({
            "analysis_id": str(analysis.get("_id", "")),
            "document_id": doc_id,
            "document_name": doc_name,
            "risk_score": risk.get("composite", 0),
            "risk_tier": risk.get("tier", "unknown"),
            "recommendation": risk.get("recommendation", "unknown"),
            "status": analysis.get("status", "unknown"),
            "processing_time_ms": analysis.get("processing_time_ms", 0),
            "branch": doc_branch,
            "uploaded_by": doc_uploaded_by,
            "created_at": (
                analysis.get("created_at").isoformat()
                if analysis.get("created_at")
                else None
            ),
            "workflow_status": workflow.get("status", "UNASSIGNED"),
            "priority": workflow.get("priority", "LOW"),
            "assigned_analyst": workflow.get("assigned_analyst"),
            "assigned_manager": workflow.get("assigned_manager")
        })

    return {"recent_activity": items, "count": len(items)}

    return {"recent_activity": items, "count": len(items)}


# ------------------------------------------------------------------ #
#  GET /risk-distribution — Count per risk tier
# ------------------------------------------------------------------ #
@router.get(
    "/risk-distribution",
    summary="Risk tier distribution",
)
async def risk_distribution(
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Count of analyses in each risk tier (low, medium, high), scoped by role."""
    analyses_col = get_collection("analyses")

    analysis_match = await get_role_analysis_match(current_user)
    match_filter = {"status": "analyzed"}
    if analysis_match:
        match_filter.update(analysis_match)

    pipeline = [
        {"$match": match_filter},
        {
            "$group": {
                "_id": "$results.risk_score.tier",
                "count": {"$sum": 1},
            }
        },
    ]

    cursor = analyses_col.aggregate(pipeline)
    distribution: dict[str, int] = {"verified": 0, "low_risk": 0, "review": 0, "high_risk": 0}
    async for entry in cursor:
        tier = entry.get("_id")
        if tier in distribution:
            distribution[tier] = entry["count"]

    total = sum(distribution.values())

    return {
        "distribution": distribution,
        "total": total,
        "percentages": {
            tier: round((count / total) * 100, 2) if total > 0 else 0.0
            for tier, count in distribution.items()
        },
    }


# ------------------------------------------------------------------ #
#  GET /trends — Daily fraud counts for last N days
# ------------------------------------------------------------------ #
@router.get(
    "/trends",
    summary="Fraud detection trends over time",
)
async def fraud_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """
    Return daily counts of total analyses and high-risk detections
    for the specified number of days, using MongoDB aggregation, scoped by role.
    """
    analyses_col = get_collection("analyses")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    analysis_match = await get_role_analysis_match(current_user)
    match_filter = {"created_at": {"$gte": cutoff}}
    if analysis_match:
        match_filter.update(analysis_match)

    pipeline = [
        {"$match": match_filter},
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at",
                    }
                },
                "total": {"$sum": 1},
                "high_risk": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$results.risk_score.tier", "high_risk"]},
                            1,
                            0,
                        ]
                    }
                },
                "review": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$results.risk_score.tier", "review"]},
                            1,
                            0,
                        ]
                    }
                },
                "low_risk": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$results.risk_score.tier", "low_risk"]},
                            1,
                            0,
                        ]
                    }
                },
                "verified": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$results.risk_score.tier", "verified"]},
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {"$sort": {"_id": 1}},
    ]

    cursor = analyses_col.aggregate(pipeline)
    daily: list[dict] = []
    async for entry in cursor:
        daily.append({
            "date": entry["_id"],
            "total_scanned": entry["total"],
            "high_risk": entry["high_risk"],
            "review": entry["review"],
            "low_risk": entry["low_risk"],
            "verified": entry["verified"],
        })

    # Fill missing dates with zeros
    filled = _fill_missing_dates(daily, days)

    return {
        "period_days": days,
        "trends": filled,
        "total_scanned": sum(d["total_scanned"] for d in filled),
        "total_high_risk": sum(d["high_risk"] for d in filled),
    }


def _fill_missing_dates(daily: list[dict], days: int) -> list[dict]:
    """Ensure every date in the range has an entry (zero-filled if missing)."""
    today = datetime.now(timezone.utc).date()
    date_map = {d["date"]: d for d in daily}
    filled: list[dict] = []

    for offset in range(days - 1, -1, -1):
        date_str = (today - timedelta(days=offset)).isoformat()
        if date_str in date_map:
            filled.append(date_map[date_str])
        else:
            filled.append({
                "date": date_str,
                "total_scanned": 0,
                "high_risk": 0,
                "review": 0,
                "low_risk": 0,
                "verified": 0,
            })

    return filled
