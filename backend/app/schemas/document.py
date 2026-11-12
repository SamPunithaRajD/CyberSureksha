"""
DocuShield AI — Document Pydantic Schemas (v2)

Request / response models used by the API layer for document operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Returned after a successful document upload."""

    document_id: str = Field(..., description="MongoDB ObjectId as string")
    filename: str
    file_hash: str = Field(default="", description="SHA-256 hash of file contents")
    status: str = Field(default="uploaded")
    message: str = Field(default="Document uploaded successfully")
    uploaded_at: Optional[datetime] = None


class DocumentResponse(BaseModel):
    """Full document metadata returned by detail / list endpoints."""

    id: str
    filename: str
    original_filename: str = ""
    file_type: str = ""
    file_size_bytes: int = 0
    thumbnail_filename: str = ""
    document_category: str = "unknown"
    status: str = "uploaded"
    uploaded_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    page_count: int = 1

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    documents: list[DocumentResponse]
    total: int
    page: int = 1
    per_page: int = 20
    total_pages: int = 1

