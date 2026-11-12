"""
Document Routes — Upload, list, retrieve, and soft-delete document records.
Handles file validation, deduplication via SHA-256 hash, and MongoDB CRUD.
"""

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from loguru import logger
from app.utils.auth_deps import get_current_user, RoleChecker

from app.database import get_collection
from app.models.document import create_document_dict, serialize_document
from app.models.case import create_case_dict
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from app.utils.file_handler import (
    compute_file_hash,
    generate_unique_filename,
    save_uploaded_file,
    validate_file_type,
)

router = APIRouter()


# ------------------------------------------------------------------ #
#  POST / — Upload a document
# ------------------------------------------------------------------ #
@router.post(
    "/",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for fraud analysis",
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "System Admin"]))
):
    """
    Accept an uploaded file, validate it, check for duplicates, persist
    to disk and MongoDB, and return a document reference.
    """
    logger.info(f"Received upload: {file.filename} ({file.content_type})")

    # --- Validate file type ---
    if not validate_file_type(file.filename):
        logger.warning(f"Rejected file type: {file.filename}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type for '{file.filename}'. "
                f"Accepted formats: PDF, PNG, JPG, JPEG, TIFF, BMP."
            ),
        )

    # --- Read contents & validate size ---
    contents = await file.read()
    max_size = 50 * 1024 * 1024  # 50 MB
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {max_size // (1024 * 1024)} MB.",
        )

    # --- Compute SHA-256 hash ---
    file_hash = compute_file_hash(contents)
    logger.debug(f"File hash: {file_hash}")

    # --- Duplicate check ---
    documents_col = get_collection("documents")
    existing = await documents_col.find_one(
        {"file_hash_sha256": file_hash, "status": {"$ne": "deleted"}}
    )
    if existing:
        logger.info(f"Duplicate detected — hash {file_hash} already exists")
        return DocumentUploadResponse(
            document_id=str(existing["_id"]),
            filename=existing.get("original_filename", file.filename),
            file_hash=file_hash,
            status="duplicate",
            message="A document with the same content already exists.",
        )

    # --- Save to disk ---
    unique_filename = generate_unique_filename(file.filename)
    from app.config import settings
    file_path = save_uploaded_file(contents, unique_filename, settings.UPLOAD_DIR)
    logger.debug(f"File saved to {file_path}")

    # --- Generate Thumbnail & Parse Page Count for PDFs ---
    thumbnail_filename = unique_filename
    page_count = 1
    if unique_filename.lower().endswith(".pdf"):
        try:
            import fitz
            doc_pdf = fitz.open(str(file_path))
            page_count = len(doc_pdf)
            doc_pdf.close()
            
            from app.utils.image_processing import pdf_to_images
            import cv2
            import os
            images = pdf_to_images(str(file_path), dpi=150)
            if images:
                thumbnail_filename = unique_filename + ".jpg"
                cv2.imwrite(os.path.join(settings.UPLOAD_DIR, thumbnail_filename), images[0])
        except Exception as e:
            logger.error(f"Failed to process PDF {unique_filename}: {e}")

    # --- Create document record ---
    doc_dict = create_document_dict(
        filename=unique_filename,
        original_filename=file.filename,
        file_type=file.content_type or "application/octet-stream",
        file_size_bytes=len(contents),
        file_hash_sha256=file_hash,
        storage_path=str(file_path),
        uploaded_by=current_user.get("username", "system"),
        page_count=page_count,
    )
    doc_dict["thumbnail_filename"] = thumbnail_filename
    doc_dict["branch"] = current_user.get("branch", "Canara Bank")

    result = await documents_col.insert_one(doc_dict)
    doc_dict["_id"] = result.inserted_id
    logger.info(f"Document created: {result.inserted_id} with page_count={page_count}")

    # Auto-wrap in a Case for backwards compatibility
    cases_col = get_collection("cases")
    case_dict = create_case_dict(
        case_name=f"Case: {file.filename}",
        uploaded_by=current_user.get("username", "system"),
        branch=current_user.get("branch", "Canara Bank"),
        document_ids=[str(result.inserted_id)],
    )
    case_res = await cases_col.insert_one(case_dict)
    
    # Save case_id back to document
    await documents_col.update_one(
        {"_id": result.inserted_id},
        {"$set": {"case_id": str(case_res.inserted_id)}}
    )

    return DocumentUploadResponse(
        document_id=str(result.inserted_id),
        filename=file.filename,
        file_hash=file_hash,
        status="uploaded",
        message="Document uploaded successfully and queued for analysis.",
    )


# ------------------------------------------------------------------ #
#  GET / — List documents (paginated)
# ------------------------------------------------------------------ #
@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List all documents with pagination",
)
async def list_documents(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status"
    ),
    category: Optional[str] = Query(None, description="Filter by document category"),
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Return paginated list of documents, optionally filtered by status/category and isolated by role/branch."""
    documents_col = get_collection("documents")

    # Build query
    query: dict = {"status": {"$ne": "deleted"}}
    if status_filter:
        query["status"] = status_filter
    if category:
        query["category"] = category

    # Enforce role-based branch/user isolation
    user_role = current_user.get("role")
    if user_role == "Underwriting Officer":
        # Underwriters only see their own uploads
        query["uploaded_by"] = current_user.get("username")
    elif user_role == "Branch Manager":
        # Managers only see their branch AND only escalated/decided cases
        query["branch"] = current_user.get("branch", "Canara Bank")
        analyses_col = get_collection("analyses")
        escalated_doc_ids = []
        async for analysis in analyses_col.find(
            {"workflow.status": {"$in": ["ESCALATED", "APPROVED", "REJECTED", "CLOSED"]}},
            {"document_id": 1}
        ):
            escalated_doc_ids.append(analysis["document_id"])
        from bson import ObjectId
        valid_oids = []
        for did in escalated_doc_ids:
            try:
                valid_oids.append(ObjectId(did))
            except Exception:
                pass
        query["_id"] = {"$in": valid_oids}
    elif user_role == "Fraud Analyst":
        # Analysts only see flagged documents or assigned cases. For simplicity, we show high_risk and review tier cases or documents with non-verified status
        query["status"] = {"$in": ["flagged", "blocked", "processing", "analyzed"]}
    # Auditors and System Admins see all documents

    # Count
    total = await documents_col.count_documents(query)

    # Fetch page
    skip = (page - 1) * per_page
    cursor = (
        documents_col.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(per_page)
    )
    docs = []
    async for doc in cursor:
        docs.append(serialize_document(doc))

    total_pages = max(1, (total + per_page - 1) // per_page)

    logger.debug(f"Listed {len(docs)} document(s) — page {page}/{total_pages} for role {user_role}")

    return DocumentListResponse(
        documents=docs,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


# ------------------------------------------------------------------ #
#  GET /{document_id} — Retrieve a single document
# ------------------------------------------------------------------ #
@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get a single document by ID",
)
async def get_document(
    document_id: str,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Fetch a document record by its MongoDB ObjectId."""
    documents_col = get_collection("documents")

    try:
        oid = ObjectId(document_id)
    except (InvalidId, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document ID format: {document_id}",
        )

    doc = await documents_col.find_one({"_id": oid, "status": {"$ne": "deleted"}})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )

    if current_user.get("role") == "Branch Manager":
        if doc.get("branch") != current_user.get("branch", "Canara Bank"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Document is outside of your branch.",
            )
        analyses_col = get_collection("analyses")
        analysis_doc = await analyses_col.find_one(
            {"document_id": document_id},
            sort=[("created_at", -1)]
        )
        if not analysis_doc or analysis_doc.get("workflow", {}).get("status") not in ("ESCALATED", "APPROVED", "REJECTED", "CLOSED"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Case has not been escalated to the Branch Manager yet.",
            )

    return DocumentResponse(**serialize_document(doc))


# ------------------------------------------------------------------ #
#  DELETE /{document_id} — Soft delete
# ------------------------------------------------------------------ #
@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Soft-delete a document",
)
async def delete_document(
    document_id: str,
    current_user: dict = Depends(RoleChecker(["System Admin"]))
):
    """Mark a document as deleted (soft delete). Does not remove the file from disk."""
    documents_col = get_collection("documents")

    try:
        oid = ObjectId(document_id)
    except (InvalidId, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document ID format: {document_id}",
        )

    result = await documents_col.update_one(
        {"_id": oid, "status": {"$ne": "deleted"}},
        {
            "$set": {
                "status": "deleted",
                "deleted_at": datetime.now(timezone.utc),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found or already deleted.",
        )

    logger.info(f"Document soft-deleted: {document_id}")
    return {"message": f"Document {document_id} has been deleted.", "status": "deleted"}


# ------------------------------------------------------------------ #
#  GET /{document_id}/page/{page_num} — Get dynamic rendered PDF page
# ------------------------------------------------------------------ #
import os
import fitz
from fastapi.responses import FileResponse

@router.get(
    "/{document_id}/page/{page_num}",
    summary="Get rendered image of a specific PDF page",
)
async def get_document_page_image(
    document_id: str,
    page_num: int
):
    """Render a specific PDF page to an image dynamically and cache it."""
    documents_col = get_collection("documents")
    try:
        oid = ObjectId(document_id)
    except (InvalidId, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document ID format: {document_id}",
        )
        
    doc = await documents_col.find_one({"_id": oid, "status": {"$ne": "deleted"}})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )
        
    file_path = doc.get("storage_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document file not found on disk.",
        )
        
    if not file_path.lower().endswith(".pdf"):
        if page_num == 1:
            return FileResponse(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page number must be 1 for non-PDF documents.",
        )
        
    try:
        doc_pdf = fitz.open(file_path)
        total_pages = len(doc_pdf)
        if page_num < 1 or page_num > total_pages:
            doc_pdf.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Page number {page_num} out of range (1 to {total_pages}).",
            )
            
        page = doc_pdf[page_num - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        
        from app.config import settings
        page_img_filename = f"{document_id}_page_{page_num}.jpg"
        page_img_path = os.path.join(settings.UPLOAD_DIR, page_img_filename)
        
        if not os.path.exists(page_img_path):
            pix.save(page_img_path)
            
        doc_pdf.close()
        return FileResponse(page_img_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to render page {page_num} for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render page image: {str(e)}"
        )

