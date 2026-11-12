"""
SecureDocXAI — Analysis MongoDB Model

Provides factory and serialization helpers for the ``analyses`` collection.
Each analysis record is tied 1-to-1 with a document via ``document_id``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId


# ── Constants ────────────────────────────────────────────────────────────────
PIPELINE_VERSION = "1.0.0"

AnalysisStatus = Literal["pending", "running", "completed", "failed"]


def create_analysis_dict(
    *,
    document_id: str,
    pipeline_version: str = PIPELINE_VERSION,
    status: str = "pending",
    results: dict[str, Any] | None = None,
    processing_time_ms: float = 0.0,
) -> dict[str, Any]:
    """Build a dict ready for ``insert_one`` into the *analyses* collection.

    Parameters
    ----------
    document_id:
        The string representation of the parent document's ``_id``.
    pipeline_version:
        Version tag of the analysis pipeline.
    status:
        Current analysis status (pending, running, completed, failed).
    results:
        Dict containing all pipeline results (ocr, metadata, tampering, etc.).
    processing_time_ms:
        Total pipeline execution time in milliseconds.

    Returns
    -------
    dict
        A MongoDB-ready analysis dict.
    """
    now = datetime.now(timezone.utc)
    res = results or {}
    return {
        "document_id": document_id,
        "pipeline_version": pipeline_version,
        "ocr_result": res.get("ocr", {}),
        "metadata_analysis": res.get("metadata", {}),
        "tampering_analysis": res.get("tampering", {}),
        "signature_analysis": res.get("signature", {}),
        "amount_analysis": res.get("amount", {}),
        "anomaly_flags": res.get("anomaly", {}).get("text_anomalies", [])
            + res.get("anomaly", {}).get("cross_field_anomalies", [])
            + res.get("anomaly", {}).get("pattern_anomalies", [])
            + res.get("anomaly", {}).get("cross_document_anomalies", [])
            + res.get("anomaly", {}).get("structured_anomalies", [])
            + res.get("anomaly", {}).get("banking_anomalies", []),
        "risk_score": res.get("risk_score", {
            "composite": 0.0,
            "sub_scores": {
                "metadata": 0.0,
                "tampering": 0.0,
                "signature": 0.0,
                "amount": 0.0,
                "anomaly": 0.0,
            },
            "tier": "low_risk",
            "recommendation": "pending",
            "detected_issues": [],
        }),
        "explanation": res.get("explanation", {
            "summary": "",
            "risk_in_words": "",
            "factors": [],
            "recommended_actions": [],
        }),
        "workflow": res.get("workflow", {
            "status": "UNASSIGNED",
            "assigned_analyst": None,
            "assigned_manager": None,
            "priority": "LOW",
            "escalation_reason": None,
            "escalated_by": None
        }),
        "audit_logs": res.get("audit_logs", []),
        "version": res.get("version", 1),
        "updated_at": now,
        "results": res,  # Store full raw results for detailed queries
        "processing_time_ms": processing_time_ms,
        "status": status,
        "started_at": now,
        "completed_at": now if status in ("analyzed", "failed") else None,
        "created_at": now,
    }


def serialize_analysis(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw MongoDB analysis document into a JSON-safe dict.

    * ``_id`` (``ObjectId``) → ``"id"`` (``str``)
    * ``datetime`` objects → ISO-8601 strings
    * Nested sub-documents are preserved as-is.
    """
    if doc is None:
        return {}

    serialized: dict[str, Any] = {}

    # Map _id → id
    if "_id" in doc:
        serialized["id"] = str(doc["_id"])

    # Scalar / nested fields — pass through
    for key in (
        "document_id",
        "pipeline_version",
        "ocr_result",
        "metadata_analysis",
        "tampering_analysis",
        "signature_analysis",
        "amount_analysis",
        "anomaly_flags",
        "risk_score",
        "explanation",
        "workflow",
        "audit_logs",
        "version",
        "results",
        "processing_time_ms",
        "status",
        "notes",
        "decisions",
    ):
        if key in doc:
            serialized[key] = doc[key]

    # Convert datetimes
    for dt_key in ("started_at", "completed_at", "updated_at"):
        val = doc.get(dt_key)
        if isinstance(val, datetime):
            serialized[dt_key] = val.isoformat()
        else:
            serialized[dt_key] = val

    # Convert datetimes in lists of dicts
    for list_key in ("notes", "decisions", "audit_logs"):
        if list_key in doc and isinstance(doc[list_key], list):
            serialized_list = []
            for item in doc[list_key]:
                if isinstance(item, dict):
                    new_item = {}
                    for k, v in item.items():
                        if isinstance(v, datetime):
                            new_item[k] = v.isoformat()
                        else:
                            new_item[k] = v
                    serialized_list.append(new_item)
                else:
                    serialized_list.append(item)
            serialized[list_key] = serialized_list

    return serialized
