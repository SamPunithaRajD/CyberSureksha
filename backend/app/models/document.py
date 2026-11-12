"""
SecureDocXAI — Document MongoDB Model

Provides factory and serialization helpers for the ``documents`` collection.
Documents are stored as plain dicts (not ODM objects) for maximum flexibility.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId


# ── Type aliases ─────────────────────────────────────────────────────────────
DocumentCategory = Literal[
    "land_record", "financial", "legal", "identity", "unknown"
]
DocumentStatus = Literal["uploaded", "processing", "analyzed", "failed"]


def create_document_dict(
    *,
    filename: str,
    original_filename: str,
    file_type: str,
    file_size_bytes: int,
    file_hash_sha256: str,
    storage_path: str,
    document_category: DocumentCategory = "unknown",
    uploaded_by: str = "system",
    page_count: int = 1,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a dict ready for ``insert_one`` into the *documents* collection.

    Parameters
    ----------
    filename:
        The on-disk (UUID-prefixed) filename.
    original_filename:
        The user-supplied original filename.
    file_type:
        MIME type or extension (e.g. ``".pdf"``).
    file_size_bytes:
        Size in bytes of the uploaded file.
    file_hash_sha256:
        SHA-256 hex digest of the file contents.
    storage_path:
        Absolute or relative path where the file is persisted.
    document_category:
        Semantic category of the document.
    uploaded_by:
        Identifier of the uploading user/service.
    page_count:
        Number of pages (default 1 for images).
    metadata:
        Arbitrary key-value metadata extracted from the file.

    Returns
    -------
    dict
        A MongoDB-ready document dict (without ``_id``; Mongo will assign one).
    """
    now = datetime.now(timezone.utc)
    return {
        "filename": filename,
        "original_filename": original_filename,
        "file_type": file_type,
        "file_size_bytes": file_size_bytes,
        "file_hash_sha256": file_hash_sha256,
        "document_category": document_category,
        "storage_path": storage_path,
        "status": "uploaded",
        "uploaded_by": uploaded_by,
        "uploaded_at": now,
        "processed_at": None,
        "metadata": metadata or {},
        "page_count": page_count,
    }


def serialize_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw MongoDB document into a JSON-safe dict.

    * ``_id`` (``ObjectId``) → ``"id"`` (``str``)
    * ``datetime`` objects → ISO-8601 strings
    """
    if doc is None:
        return {}

    serialized: dict[str, Any] = {}

    # Map _id → id
    if "_id" in doc:
        serialized["id"] = str(doc["_id"])

    # Copy scalar / simple fields
    for key in (
        "filename",
        "original_filename",
        "file_type",
        "file_size_bytes",
        "file_hash_sha256",
        "document_category",
        "storage_path",
        "status",
        "uploaded_by",
        "page_count",
        "metadata",
        "thumbnail_filename",
    ):
        if key in doc:
            serialized[key] = doc[key]

    # Convert datetimes
    for dt_key in ("uploaded_at", "processed_at"):
        val = doc.get(dt_key)
        if isinstance(val, datetime):
            serialized[dt_key] = val.isoformat()
        else:
            serialized[dt_key] = val

    return serialized
