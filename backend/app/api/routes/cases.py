"""
Cases Routes — Create, list, retrieve, and transition investigation cases.
Also runs case-level Multi-Document AI analysis (ViT, LLM, Relationship Engine).
"""

import time
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from loguru import logger

from app.database import get_collection
from app.models.case import CasePriority, CaseStatus, create_case_dict, serialize_case
from app.models.document import create_document_dict, serialize_document
from app.models.analysis import create_analysis_dict
from app.utils.auth_deps import RoleChecker, get_current_user
from app.utils.file_handler import (
    compute_file_hash,
    generate_unique_filename,
    save_uploaded_file,
    validate_file_type,
)

# AI Pipeline Services
from app.services.ocr_engine import OCREngine
from app.services.metadata_extractor import MetadataExtractor
from app.services.tampering_detector import TamperingDetector
from app.services.signature_verifier import SignatureVerifier
from app.services.amount_detector import AmountDetector
from app.services.anomaly_detector import AnomalyDetector
from app.services.explainable_ai import ExplainableAI
from app.services.risk_scorer import RiskScorer
from app.services.vit_pipeline import VisionTransformerPipeline
from app.services.llm_reasoning import LLMReasoningEngine
from app.services.relationship_engine import DocumentRelationshipEngine
from app.services.correlation_graph import DocumentCorrelationGraphEngine

router = APIRouter()

# ── Helper to convert ID ──────────────────────────────────────────────────────
def _case_to_object_id(id_str: str, label: str = "Case ID") -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label} format: {id_str}",
        )

# ── Helper to resolve doc types ───────────────────────────────────────────────
def _infer_mime_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return "pdf"
    elif ext in ("png", "jpg", "jpeg", "tiff", "tif", "bmp"):
        return "image"
    return "unknown"


# ── POST /upload — Upload multiple documents into a Case ─────────────────────
@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple documents and create an investigation case",
)
async def upload_case_documents(
    files: list[UploadFile] = File(...),
    case_name: Optional[str] = None,
    priority: CasePriority = "LOW",
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "System Admin"]))
):
    """
    Accept multiple uploaded files, validate them, save to disk/DB,
    group them into a new Case, and trigger immediate synchronous analysis.
    """
    logger.info("Received multi-document upload of {} files", len(files))
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files uploaded.",
        )

    # 1. Verify and save documents
    doc_ids = []
    documents_col = get_collection("documents")
    from app.config import settings

    for f in files:
        if not validate_file_type(f.filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type for '{f.filename}'",
            )
        
        contents = await f.read()
        if len(contents) > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{f.filename}' exceeds 50MB limit.",
            )

        file_hash = compute_file_hash(contents)
        
        # Check duplicate
        existing = await documents_col.find_one(
            {"file_hash_sha256": file_hash, "status": {"$ne": "deleted"}}
        )
        if existing:
            doc_ids.append(str(existing["_id"]))
            continue

        unique_filename = generate_unique_filename(f.filename)
        file_path = save_uploaded_file(contents, unique_filename, settings.UPLOAD_DIR)
        
        # Thumbnail and Page Count
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
            except Exception as exc:
                logger.error("Failed to generate PDF metrics: {}", exc)

        # Create doc record
        doc_dict = create_document_dict(
            filename=unique_filename,
            original_filename=f.filename,
            file_type=f.content_type or "application/octet-stream",
            file_size_bytes=len(contents),
            file_hash_sha256=file_hash,
            storage_path=str(file_path),
            uploaded_by=current_user.get("username", "system"),
            page_count=page_count,
        )
        doc_dict["thumbnail_filename"] = thumbnail_filename
        doc_dict["branch"] = current_user.get("branch", "Canara Bank")
        
        # Tag category based on keyword
        f_lower = f.filename.lower()
        if "bank" in f_lower or "statement" in f_lower:
            doc_dict["document_category"] = "financial"
        elif "payslip" in f_lower or "salary" in f_lower:
            doc_dict["document_category"] = "financial"
        elif "pan" in f_lower:
            doc_dict["document_category"] = "identity"
        elif "aadhaar" in f_lower or "adhar" in f_lower:
            doc_dict["document_category"] = "identity"
        elif "passport" in f_lower:
            doc_dict["document_category"] = "identity"

        res = await documents_col.insert_one(doc_dict)
        doc_ids.append(str(res.inserted_id))

    # 2. Create the Investigation Case
    resolved_case_name = case_name or f"Case: {files[0].filename} & {len(files)-1} details" if len(files) > 1 else f"Case: {files[0].filename}"
    cases_col = get_collection("cases")
    case_dict = create_case_dict(
        case_name=resolved_case_name,
        uploaded_by=current_user.get("username", "system"),
        branch=current_user.get("branch", "Canara Bank"),
        document_ids=doc_ids,
        priority=priority,
    )
    
    result = await cases_col.insert_one(case_dict)
    case_id = str(result.inserted_id)
    
    # Associate Case ID back to documents
    await documents_col.update_many(
        {"_id": {"$in": [ObjectId(did) for did in doc_ids]}},
        {"$set": {"case_id": case_id}}
    )

    # 3. Synchronously run multi-doc analysis
    await analyze_case_internal(case_id, current_user.get("username", "system"))

    # Fetch updated case
    updated_case = await cases_col.find_one({"_id": ObjectId(case_id)})
    return serialize_case(updated_case)


# ── GET / — List Cases ────────────────────────────────────────────────────────
@router.get(
    "/",
    summary="List and filter investigation cases with role branch isolation",
)
async def list_cases(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    cases_col = get_collection("cases")
    
    # RBAC matching query
    query: dict = {}
    
    user_role = current_user.get("role")
    branch = current_user.get("branch", "Canara Bank")
    
    if user_role == "Underwriting Officer":
        query["uploaded_by"] = current_user.get("username")
    elif user_role == "Branch Manager":
        query["branch"] = branch
        query["status"] = {"$in": ["ESCALATED", "APPROVED", "REJECTED", "CLOSED"]}
    elif user_role == "Fraud Analyst":
        # Can see active review stages
        query["status"] = {"$in": ["UNASSIGNED", "UNDER_REVIEW", "ESCALATED", "APPROVED", "REJECTED", "CLOSED"]}
    
    if status:
        query["status"] = status
    if priority:
        query["priority"] = priority
    if search:
        query["$or"] = [
            {"case_name": {"$regex": search, "$options": "i"}},
            {"case_id": {"$regex": search, "$options": "i"}},
        ]
        
    total = await cases_col.count_documents(query)
    skip = (page - 1) * per_page
    cursor = cases_col.find(query).sort("created_at", -1).skip(skip).limit(per_page)
    
    cases = []
    async for c in cursor:
        cases.append(serialize_case(c))
        
    return {
        "cases": cases,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page)
    }


# ── GET /{case_id} — Fetch single case with nested documents ──────────────────
@router.get(
    "/{case_id}",
    summary="Get detailed case info and nested document metadata",
)
async def get_case(
    case_id: str,
    current_user: dict = Depends(get_current_user),
):
    cases_col = get_collection("cases")
    documents_col = get_collection("documents")
    
    case_obj = await cases_col.find_one({"_id": ObjectId(case_id)})
    if not case_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found.",
        )

    # Nest full document details
    doc_ids = case_obj.get("document_ids", [])
    documents = []
    async for d in documents_col.find({"_id": {"$in": [ObjectId(did) for did in doc_ids]}}):
        documents.append(serialize_document(d))

    serialized = serialize_case(case_obj)
    serialized["documents"] = documents
    return serialized


# ── POST /{case_id}/analyze — Trigger full Multi-Document AI analysis ───────
@router.post(
    "/{case_id}/analyze",
    summary="Run full modular pipeline: OCR, ViT, relationship validation, LLM summaries",
)
async def trigger_case_analysis(
    case_id: str,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "System Admin"]))
):
    await analyze_case_internal(case_id, current_user.get("username", "system"))
    cases_col = get_collection("cases")
    case_obj = await cases_col.find_one({"_id": ObjectId(case_id)})
    return serialize_case(case_obj)


# ── POST /{case_id}/notes — Add investigator comment ──────────────────────────
@router.post(
    "/{case_id}/notes",
    summary="Add an investigator comment to the case audit ledger",
)
async def add_case_note(
    case_id: str,
    note: dict,
    current_user: dict = Depends(get_current_user),
):
    cases_col = get_collection("cases")
    text = note.get("text", "").strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="Note text cannot be empty."
        )
        
    now = datetime.now(timezone.utc)
    new_note = {
        "username": current_user.get("username", "system"),
        "role": current_user.get("role", "Underwriter"),
        "text": text,
        "created_at": now
    }
    
    log_entry = {
        "action": "NOTE_ADDED",
        "performed_by": current_user.get("username", "system"),
        "timestamp": now,
        "details": f"Added comment: '{text[:50]}...'"
    }

    result = await cases_col.update_one(
        {"_id": ObjectId(case_id)},
        {
            "$push": {
                "notes": new_note,
                "audit_logs": log_entry
            },
            "$set": {"updated_at": now}
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Case not found")
        
    return {"status": "success", "note": new_note}


# ── POST /{case_id}/assign — Assign to analyst ────────────────────────────────
@router.post(
    "/{case_id}/assign",
    summary="Assign a case to an analyst",
)
async def assign_case(
    case_id: str,
    current_user: dict = Depends(RoleChecker(["Fraud Analyst", "Branch Manager", "System Admin"]))
):
    cases_col = get_collection("cases")
    now = datetime.now(timezone.utc)
    analyst_name = current_user.get("username")
    
    log_entry = {
        "action": "CASE_ASSIGNED",
        "performed_by": analyst_name,
        "timestamp": now,
        "details": f"Assigned case for verification to {analyst_name}."
    }

    await cases_col.update_one(
        {"_id": ObjectId(case_id)},
        {
            "$set": {
                "assigned_analyst": analyst_name,
                "status": "UNDER_REVIEW",
                "updated_at": now
            },
            "$push": {"audit_logs": log_entry}
        }
    )
    return {"status": "success", "assigned_analyst": analyst_name}


# ── POST /{case_id}/escalate — Escalate to manager ────────────────────────────
@router.post(
    "/{case_id}/escalate",
    summary="Escalate case to Branch Manager",
)
async def escalate_case(
    case_id: str,
    payload: dict,
    current_user: dict = Depends(RoleChecker(["Fraud Analyst", "System Admin"]))
):
    cases_col = get_collection("cases")
    reason = payload.get("reason", "Escalated for senior review.")
    now = datetime.now(timezone.utc)
    
    log_entry = {
        "action": "CASE_ESCALATED",
        "performed_by": current_user.get("username"),
        "timestamp": now,
        "details": f"Escalated to Branch Manager. Reason: {reason}"
    }

    await cases_col.update_one(
        {"_id": ObjectId(case_id)},
        {
            "$set": {
                "status": "ESCALATED",
                "updated_at": now
            },
            "$push": {
                "decisions": {
                    "role": "Fraud Analyst",
                    "action": "ESCALATE",
                    "justification": reason,
                    "performed_by": current_user.get("username"),
                    "timestamp": now
                },
                "audit_logs": log_entry
            }
        }
    )
    return {"status": "success", "status_new": "ESCALATED"}


# ── POST /{case_id}/decide — Manager Decision ────────────────────────────────
@router.post(
    "/{case_id}/decide",
    summary="Final manager decision (Approve / Reject / Waitlist)",
)
async def decide_case(
    case_id: str,
    payload: dict,
    current_user: dict = Depends(RoleChecker(["Branch Manager", "System Admin"]))
):
    cases_col = get_collection("cases")
    decision = payload.get("decision", "").upper()
    justification = payload.get("justification", "").strip()
    
    if decision not in ("APPROVED", "REJECTED", "CLOSED", "WAITLISTED"):
        raise HTTPException(status_code=400, detail="Invalid decision option.")
        
    now = datetime.now(timezone.utc)
    
    log_entry = {
        "action": f"CASE_{decision}",
        "performed_by": current_user.get("username"),
        "timestamp": now,
        "details": f"Case decision set to {decision}. Justification: {justification}"
    }

    await cases_col.update_one(
        {"_id": ObjectId(case_id)},
        {
            "$set": {
                "status": decision,
                "assigned_manager": current_user.get("username"),
                "updated_at": now
            },
            "$push": {
                "decisions": {
                    "role": "Branch Manager",
                    "action": decision,
                    "justification": justification,
                    "performed_by": current_user.get("username"),
                    "timestamp": now
                },
                "audit_logs": log_entry
            }
        }
    )
    return {"status": "success", "status_new": decision}


# ── POST /{case_id}/qa — Interactive Chat Q&A with LLM Reasoning ──────────────
@router.post(
    "/{case_id}/qa",
    summary="Query case documents and receive reasoned responses",
)
async def qa_case_documents(
    case_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    cases_col = get_collection("cases")
    documents_col = get_collection("documents")
    
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
        
    case_obj = await cases_col.find_one({"_id": ObjectId(case_id)})
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")
        
    # Gather document data
    doc_ids = case_obj.get("document_ids", [])
    documents = []
    async for d in documents_col.find({"_id": {"$in": [ObjectId(did) for did in doc_ids]}}):
        documents.append(d)
        
    llm = LLMReasoningEngine()
    anomalies = case_obj.get("risk_score", {}).get("detected_issues", [])
    
    answer = llm.answer_query(question, documents, anomalies)
    return {"question": question, "answer": answer}


# ── GET /{case_id}/report — Download styling HTML Printable report ───────────
@router.get(
    "/{case_id}/report",
    summary="Download print-friendly audit-ready HTML report",
)
async def generate_styled_report(
    case_id: str,
    current_user: dict = Depends(get_current_user)
):
    cases_col = get_collection("cases")
    documents_col = get_collection("documents")
    
    case_obj = await cases_col.find_one({"_id": ObjectId(case_id)})
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")
        
    doc_ids = case_obj.get("document_ids", [])
    documents = []
    async for d in documents_col.find({"_id": {"$in": [ObjectId(did) for did in doc_ids]}}):
        documents.append(d)

    # Render a gorgeous printable HTML page directly
    case_id_str = case_obj.get("case_id")
    case_name = case_obj.get("case_name")
    status_val = case_obj.get("status")
    priority_val = case_obj.get("priority")
    risk_comp = case_obj.get("risk_score", {}).get("composite", 0.0)
    risk_tier = case_obj.get("risk_score", {}).get("display_tier", "LOW RISK")
    trust_val = case_obj.get("trust_score", {}).get("score", 100.0)
    trust_cat = case_obj.get("trust_score", {}).get("category", "High Trust")
    summary = case_obj.get("explanation", {}).get("executive_summary", "")
    narrative = case_obj.get("explanation", {}).get("narrative", "")
    
    doc_rows = []
    for d in documents:
        doc_rows.append(f"""
        <tr>
            <td><strong>{d.get('original_filename')}</strong></td>
            <td>{d.get('document_category', 'unknown').upper()}</td>
            <td>{d.get('page_count')}</td>
            <td>{d.get('status')}</td>
        </tr>
        """)
        
    anom_rows = []
    anomalies = case_obj.get("risk_score", {}).get("detected_issues", [])
    for a in anomalies:
        anom_rows.append(f"""
        <div class="anomaly-item">
            <span class="badge badge-{a.get('severity', 'medium').lower()}">{a.get('severity')}</span>
            <strong>{a.get('issue')}</strong>
            <p style="margin: 5px 0 0 0; font-size: 13px; color: #52525b;">Recommendation: {a.get('recommendation')}</p>
        </div>
        """)
        
    audit_rows = []
    for l in case_obj.get("audit_logs", []):
        ts = l.get("timestamp").strftime("%Y-%m-%d %H:%M:%S") if isinstance(l.get("timestamp"), datetime) else str(l.get("timestamp"))
        audit_rows.append(f"""
        <tr>
            <td>{ts}</td>
            <td><strong>{l.get('action')}</strong></td>
            <td>{l.get('performed_by')}</td>
            <td>{l.get('details')}</td>
        </tr>
        """)

    decision_rows = []
    for dec in case_obj.get("decisions", []):
        ts = dec.get("timestamp").strftime("%Y-%m-%d %H:%M:%S") if isinstance(dec.get("timestamp"), datetime) else str(dec.get("timestamp"))
        decision_rows.append(f"""
        <div class="decision-item">
            <strong>{dec.get('role')} Decision: {dec.get('action')}</strong><br/>
            <span style="font-size:12px; color:#71717a;">Performed by: {dec.get('performed_by')} on {ts}</span>
            <p style="margin: 8px 0 0 0; font-style: italic;">"Justification: {dec.get('justification')}"</p>
        </div>
        """)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>SecureDocXAI Case Investigation Report - {case_id_str}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                color: #09090b;
                line-height: 1.5;
                padding: 40px;
                background-color: #ffffff;
            }}
            .header {{
                border-bottom: 2px solid #e4e4e7;
                padding-bottom: 20px;
                margin-bottom: 30px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .brand {{
                font-size: 26px;
                font-weight: 800;
                color: #0f172a;
            }}
            .brand span {{
                color: #2563eb;
            }}
            .case-meta {{
                font-size: 14px;
                color: #4b5563;
                text-align: right;
            }}
            .section {{
                margin-bottom: 35px;
            }}
            .section-title {{
                font-size: 18px;
                font-weight: 700;
                border-bottom: 1px solid #f3f4f6;
                padding-bottom: 8px;
                margin-bottom: 15px;
                color: #1e293b;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 15px;
                margin-bottom: 25px;
            }}
            .card {{
                border: 1px solid #e4e4e7;
                border-radius: 8px;
                padding: 15px;
                text-align: center;
                background-color: #fafafa;
            }}
            .card-val {{
                font-size: 24px;
                font-weight: 800;
                margin-top: 5px;
            }}
            .card-lbl {{
                font-size: 12px;
                font-weight: 500;
                color: #71717a;
                text-transform: uppercase;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }}
            th {{
                background-color: #f4f4f5;
                text-align: left;
                padding: 10px;
                font-weight: 600;
                border-bottom: 2px solid #e4e4e7;
                font-size: 13px;
            }}
            td {{
                padding: 10px;
                border-bottom: 1px solid #e4e4e7;
                font-size: 13px;
            }}
            .anomaly-item {{
                background-color: #fffafb;
                border-left: 4px solid #f43f5e;
                border: 1px solid #fecdd3;
                border-left-width: 4px;
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 12px;
            }}
            .badge {{
                display: inline-block;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 700;
                border-radius: 4px;
                text-transform: uppercase;
                margin-right: 8px;
            }}
            .badge-critical {{ background-color: #ffe4e6; color: #e11d48; }}
            .badge-high {{ background-color: #ffedd5; color: #ea580c; }}
            .badge-medium {{ background-color: #fef9c3; color: #ca8a04; }}
            .badge-low {{ background-color: #dcfce7; color: #16a34a; }}
            .decision-item {{
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 12px;
            }}
            @media print {{
                body {{ padding: 0; }}
                button {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <div class="brand">Secure<span>DocXAI</span></div>
                <div style="font-size:12px; color:#6b7280; font-weight: 500;">Explainable Multi-Document Risk Scoring & Fraud Intelligence</div>
            </div>
            <div class="case-meta">
                <strong>CASE ID: {case_id_str}</strong><br/>
                Printed on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}<br/>
                Branch: {case_obj.get('branch', 'Canara Bank')}
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-lbl">Composite Risk Score</div>
                <div class="card-val" style="color:#e11d48;">{risk_comp}%</div>
                <div class="card-lbl" style="font-size:11px; color:#e11d48; margin-top:2px;">{risk_tier}</div>
            </div>
            <div class="card">
                <div class="card-lbl">Trust Score</div>
                <div class="card-val" style="color:#16a34a;">{trust_val}%</div>
                <div class="card-lbl" style="font-size:11px; color:#16a34a; margin-top:2px;">{trust_cat}</div>
            </div>
            <div class="card">
                <div class="card-lbl">Case Status</div>
                <div class="card-val" style="color:#2563eb; font-size: 20px; line-height:36px;">{status_val}</div>
            </div>
            <div class="card">
                <div class="card-lbl">Priority</div>
                <div class="card-val" style="color:#ea580c; font-size: 20px; line-height:36px;">{priority_val}</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Executive Summary (LLM Generated)</div>
            <p><strong>{summary}</strong></p>
            <p style="font-size:14px; color:#374151; white-space: pre-line;">{narrative}</p>
        </div>

        <div class="section">
            <div class="section-title">Case Document Inventory</div>
            <table>
                <thead>
                    <tr>
                        <th>Document Name</th>
                        <th>Category</th>
                        <th>Pages</th>
                        <th>Extraction Status</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(doc_rows)}
                </tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-title">Detected Case Anomalies ({len(anomalies)})</div>
            {"".join(anom_rows) if anomalies else "<p style='color:#71717a; font-style:italic;'>No active anomalies recorded on this case.</p>"}
        </div>

        <div class="section">
            <div class="section-title">Case Decisions Ledger</div>
            {"".join(decision_rows) if case_obj.get('decisions') else "<p style='color:#71717a; font-style:italic;'>No formal review decisions signed off yet.</p>"}
        </div>

        <div class="section" style="page-break-before: always;">
            <div class="section-title">Case Activity Audit Ledger</div>
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Action</th>
                        <th>User</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(audit_rows)}
                </tbody>
            </table>
        </div>

        <script>
            window.onload = function() {{
                // Automatically open Print modal for saving
                // window.print();
            }}
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)


# ── Internal Core Pipeline execution ──────────────────────────────────────────
async def analyze_case_internal(case_id: str, username: str = "system"):
    """
    Modular execution of the multi-document AI processing pipeline:
    1. Loads all case documents.
    2. Runs individual analysis (OCR -> metadata -> tampering -> signature -> amount -> anomaly -> risk -> XAI) for documents that aren't analyzed.
    3. Executes the Vision Transformer Layout Pipeline.
    4. Executes the Document Relationship Engine cross-validating the files.
    5. Executes the Document Correlation Graph Engine.
    6. Executes the LLM Reasoning Engine (generating narratives and reports).
    7. Calculates case Trust and Financial Risk scores.
    8. Updates the database and case workflow state.
    """
    cases_col = get_collection("cases")
    documents_col = get_collection("documents")
    analyses_col = get_collection("analyses")
    
    logger.info("Initializing background case analysis pipeline for ID: {}", case_id)
    
    case_obj = await cases_col.find_one({"_id": ObjectId(case_id)})
    if not case_obj:
        logger.error("Case ID {} not found in database", case_id)
        return

    doc_ids = case_obj.get("document_ids", [])
    
    # ── A. Run individual analyses ────────────────────────────────────────────
    doc_results = []
    
    # Instantiate core analysis tools
    ocr_engine = OCREngine()
    meta_extractor = MetadataExtractor()
    tampering_detector = TamperingDetector()
    sig_verifier = SignatureVerifier()
    amount_detector = AmountDetector()
    anomaly_detector = AnomalyDetector()
    risk_scorer = RiskScorer()
    explainable_ai = ExplainableAI()
    vit_pipeline = VisionTransformerPipeline()

    for did in doc_ids:
        doc = await documents_col.find_one({"_id": ObjectId(did)})
        if not doc:
            continue
            
        file_path = doc.get("storage_path")
        file_type = _infer_mime_type(doc.get("original_filename", ""))
        
        # Check if individual analysis completed, otherwise run it
        analysis_doc = await analyses_col.find_one({"document_id": did})
        
        if not analysis_doc or doc.get("status") in ("uploaded", "processing"):
            logger.info("Running complete extraction pipeline on Document ID: {}", did)
            
            # Update doc state to processing
            await documents_col.update_one({"_id": ObjectId(did)}, {"$set": {"status": "processing"}})
            
            t0 = time.perf_counter()
            try:
                # 1. OCR
                ocr_result = ocr_engine.process_document(file_path, file_type)
                
                # 2. Correct OCR
                try:
                    from app.services.ocr_correction import OCRCorrectionLayer
                    ocr_result = OCRCorrectionLayer().correct(ocr_result)
                except Exception as e:
                    logger.warning("OCR correction failed: {}", e)

                # 3. Metadata
                metadata_result = meta_extractor.process(file_path, file_type)
                
                # 4. Tampering
                tampering_result = tampering_detector.process(None) # image-less default
                if file_type != "pdf":
                    try:
                        from app.utils.image_processing import load_image
                        img = load_image(file_path)
                        tampering_result = tampering_detector.process(img)
                    except Exception:
                        pass
                
                # 5. Signatures
                signature_result = {"signatures_found": 0, "anomalies": [], "risk_score": 0.0}
                
                # 6. Amounts
                full_text = ocr_result.get("extraction", {}).get("full_text", "")
                structured = ocr_result.get("structured_data", {})
                amount_result = amount_detector.process(full_text, structured)
                
                # 7. Anomaly Detector
                entities = ocr_result.get("entities", {})
                anomaly_result = anomaly_detector.process(
                    ocr_result,
                    metadata_result,
                    entities,
                    []
                )
                
                # 8. Single Risk Scorer
                risk_result = risk_scorer.process(
                    ocr_result=ocr_result,
                    metadata_result=metadata_result,
                    tampering_result=tampering_result,
                    signature_result=signature_result,
                    amount_result=amount_result,
                    anomaly_result=anomaly_result
                )
                
                xai_result = explainable_ai.generate_explanation(
                    risk_result,
                    metadata_result,
                    tampering_result,
                    signature_result,
                    amount_result,
                    anomaly_result
                )
                
                # Collect pipeline output
                results_dict = {
                    "ocr": ocr_result,
                    "metadata": metadata_result,
                    "tampering": tampering_result,
                    "signature": signature_result,
                    "amount": amount_result,
                    "anomaly": anomaly_result,
                    "risk_score": risk_result,
                    "explanation": xai_result,
                    "workflow": {
                        "status": "UNASSIGNED",
                        "assigned_analyst": None,
                        "assigned_manager": None,
                        "priority": "LOW"
                    }
                }
                
                # Create analysis record
                p_time = (time.perf_counter() - t0) * 1000.0
                new_analysis = create_analysis_dict(
                    document_id=did,
                    status="completed",
                    results=results_dict,
                    processing_time_ms=p_time
                )
                
                if analysis_doc:
                    await analyses_col.replace_one({"document_id": did}, new_analysis)
                else:
                    await analyses_col.insert_one(new_analysis)
                    
                analysis_doc = new_analysis
                await documents_col.update_one({"_id": ObjectId(did)}, {"$set": {"status": "analyzed"}})
                
            except Exception as exc:
                logger.error("Single document pipeline crashed on ID {}: {}", did, exc)
                await documents_col.update_one({"_id": ObjectId(did)}, {"$set": {"status": "failed"}})
                continue

        # Add result values to accumulator
        doc_results.append({
            "id": did,
            "original_filename": doc.get("original_filename", ""),
            "document_category": doc.get("document_category", "unknown"),
            "ocr_result": analysis_doc.get("ocr_result", {}),
            "metadata_analysis": analysis_doc.get("metadata_analysis", {}),
            "tampering_analysis": analysis_doc.get("tampering_analysis", {}),
            "risk_score": analysis_doc.get("risk_score", {})
        })

    # ── B. Run Vision Transformer Layout ──────────────────────────────────────
    logger.info("Executing Vision Transformer visual extraction pipeline on case docs...")
    for idx, doc_item in enumerate(doc_results):
        did = doc_item["id"]
        doc_db = await documents_col.find_one({"_id": ObjectId(did)})
        file_path = doc_db.get("storage_path")
        file_type = _infer_mime_type(doc_db.get("original_filename", ""))
        
        # Execute ViT
        vit_output = vit_pipeline.process(file_path, file_type)
        
        # Update Document record with ViT results
        await documents_col.update_one(
            {"_id": ObjectId(did)},
            {"$set": {"vit_analysis": vit_output}}
        )
        
        # Enrich temporary memory dict
        doc_item["vit_analysis"] = vit_output
        
        # If ViT found tampering, update the doc's tampering score
        if vit_output.get("visual_tampering", {}).get("detected"):
            await analyses_col.update_one(
                {"document_id": did},
                {
                    "$set": {
                        "tampering_analysis.visual_tampering": vit_output["visual_tampering"],
                        "risk_score.sub_scores.tampering": vit_output["visual_tampering"]["tampering_factor"]
                    }
                }
            )

    # ── C. Cross-Document Relationship Audit ──────────────────────────────────
    relationship_engine = DocumentRelationshipEngine()
    cross_anomalies = relationship_engine.process(doc_results)
    
    # ── D. Correlation Graph construction ─────────────────────────────────────
    graph_engine = DocumentCorrelationGraphEngine()
    corr_graph = graph_engine.build_graph(doc_results, cross_anomalies)

    # ── E. Risk & Trust scoring ───────────────────────────────────────────────
    case_scores = risk_scorer.calculate_case_scores(doc_results, cross_anomalies)

    # ── F. LLM Reasoning Narrative & Report ───────────────────────────────────
    llm = LLMReasoningEngine()
    narrative_report = llm.generate_narrative_report(
        case_details=case_obj,
        documents=doc_results,
        anomalies=cross_anomalies,
        risk_score=case_scores["composite"],
        trust_score=case_scores["trust_score"]["score"]
    )

    # ── G. Save state and Audit logs ──────────────────────────────────────────
    now = datetime.now(timezone.utc)
    log_entry = {
        "action": "CASE_ANALYZED",
        "performed_by": username,
        "timestamp": now,
        "details": (
            f"Cross-document AI verification completed. "
            f"Risk score: {case_scores['composite']}% ({case_scores['display_tier']}). "
            f"Trust: {case_scores['trust_score']['score']}%."
        )
    }

    # Aggregate case priority based on composite score
    calculated_priority: CasePriority = "LOW"
    if case_scores["composite"] >= 70:
        calculated_priority = "CRITICAL"
    elif case_scores["composite"] >= 45:
        calculated_priority = "HIGH"
    elif case_scores["composite"] >= 25:
        calculated_priority = "MEDIUM"

    await cases_col.update_one(
        {"_id": ObjectId(case_id)},
        {
            "$set": {
                "risk_score": case_scores,
                "trust_score": case_scores["trust_score"],
                "explanation": narrative_report,
                "correlation_graph": corr_graph,
                "priority": calculated_priority,
                "updated_at": now
            },
            "$push": {"audit_logs": log_entry}
        }
    )
    logger.success("Multi-document Case ID {} analysis successfully completed", case_id)
