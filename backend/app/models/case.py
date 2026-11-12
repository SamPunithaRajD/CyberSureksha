"""
SecureDocXAI — Investigation Case MongoDB Model

Provides factory and serialization helpers for the ``cases`` collection.
A Case groups multiple documents, aggregates their individual analysis result,
and runs cross-document validation engines.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timezone
from typing import Any, Literal

CaseStatus = Literal["UNASSIGNED", "UNDER_REVIEW", "ESCALATED", "APPROVED", "REJECTED", "CLOSED"]
CasePriority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def generate_case_id() -> str:
    """Generate a unique readable case identifier, e.g. CASE-20260721-AB12."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"CASE-{date_str}-{random_str}"


def create_case_dict(
    *,
    case_name: str,
    uploaded_by: str = "system",
    branch: str = "Canara Bank",
    document_ids: list[str] | None = None,
    priority: CasePriority = "LOW",
    status: CaseStatus = "UNASSIGNED",
) -> dict[str, Any]:
    """Build a dict ready for ``insert_one`` into the *cases* collection."""
    now = datetime.now(timezone.utc)
    return {
        "case_id": generate_case_id(),
        "case_name": case_name,
        "status": status,
        "priority": priority,
        "document_ids": document_ids or [],
        "uploaded_by": uploaded_by,
        "branch": branch,
        "assigned_analyst": None,
        "assigned_manager": None,
        "risk_score": {
            "composite": 0.0,
            "tier": "low_risk",
            "recommendation": "pending",
            "detected_issues": [],
            "sub_scores": {
                "metadata": 0.0,
                "tampering": 0.0,
                "signature": 0.0,
                "amount": 0.0,
                "anomaly": 0.0,
                "cross_document": 0.0
            }
        },
        "trust_score": {
            "score": 100.0,
            "category": "High Trust",
            "sub_scores": {
                "identity": 100.0,
                "financial": 100.0,
                "document": 100.0,
                "metadata": 100.0
            }
        },
        "explanation": {
            "summary": "Case initialized. Awaiting deep AI analysis.",
            "executive_summary": "Case initialized. Awaiting deep AI analysis.",
            "risk_in_words": "Low Risk",
            "factors": [],
            "recommended_actions": [],
            "narrative": ""
        },
        "correlation_graph": {
            "nodes": [],
            "edges": []
        },
        "notes": [],
        "decisions": [],
        "audit_logs": [
            {
                "action": "CASE_CREATED",
                "performed_by": uploaded_by,
                "timestamp": now,
                "details": f"Investigation case created with {len(document_ids or [])} documents."
            }
        ],
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }


def serialize_case(case: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw MongoDB case document into a JSON-safe dict."""
    if case is None:
        return {}

    serialized: dict[str, Any] = {}

    if "_id" in case:
        serialized["id"] = str(case["_id"])

    # Basic scalar / structure copy
    for key in (
        "case_id",
        "case_name",
        "status",
        "priority",
        "document_ids",
        "uploaded_by",
        "branch",
        "assigned_analyst",
        "assigned_manager",
        "risk_score",
        "trust_score",
        "explanation",
        "correlation_graph",
        "version",
    ):
        if key in case:
            serialized[key] = case[key]

    # Convert datetimes
    for dt_key in ("created_at", "updated_at"):
        val = case.get(dt_key)
        if isinstance(val, datetime):
            serialized[dt_key] = val.isoformat()
        else:
            serialized[dt_key] = val

    # Nested structures conversion
    for list_key in ("notes", "decisions", "audit_logs"):
        if list_key in case and isinstance(case[list_key], list):
            ser_list = []
            for item in case[list_key]:
                if isinstance(item, dict):
                    new_item = {}
                    for k, v in item.items():
                        if isinstance(v, datetime):
                            new_item[k] = v.isoformat()
                        else:
                            new_item[k] = v
                    ser_list.append(new_item)
                else:
                    ser_list.append(item)
            serialized[list_key] = ser_list

    return serialized
