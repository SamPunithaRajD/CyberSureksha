"""
Analysis Routes — Trigger the full fraud-analysis pipeline, retrieve results,
and query individual analysis facets (anomalies, risk score, explanation).
"""
from typing import Optional, Any
import time
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from app.utils.auth_deps import get_current_user, RoleChecker
from loguru import logger

from app.database import get_collection
from app.models.analysis import create_analysis_dict, serialize_analysis
from app.schemas.analysis import (
    AnalysisResponse,
    AnalysisTriggerResponse,
    AnomalyDetail,
    ExplanationFactor,
    ExplanationResponse,
    RiskScoreResponse,
    SubScores,
)
from app.services.anomaly_detector import AnomalyDetector
from app.services.explainable_ai import ExplainableAI
from app.services.risk_scorer import RiskScorer
from app.utils.file_handler import validate_file_type
from app.utils.image_processing import load_image, pdf_to_images

# Service imports — built in parallel by teammates
from app.services.ocr_engine import OCREngine
from app.services.metadata_extractor import MetadataExtractor
from app.services.tampering_detector import TamperingDetector
from app.services.signature_verifier import SignatureVerifier
from app.services.amount_detector import AmountDetector

router = APIRouter()


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #
def _to_object_id(id_str: str, label: str = "ID") -> ObjectId:
    """Convert a string to ObjectId, raising a clean 400 on invalid format."""
    try:
        return ObjectId(id_str)
    except (InvalidId, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label} format: {id_str}",
        )


def _determine_file_type(filename: str) -> str:
    """Infer a normalised file type from the filename extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return "pdf"
    elif ext in ("png", "jpg", "jpeg", "tiff", "tif", "bmp"):
        return "image"
    return "unknown"


async def create_notification(db, recipient_username: str, document_id: str, document_name: str, message: str, type: str):
    """Insert a new alert notification for a specific user into MongoDB."""
    notifications_col = db["notifications"]
    await notifications_col.insert_one({
        "username": recipient_username,
        "document_id": document_id,
        "document_name": document_name,
        "message": message,
        "type": type,
        "read": False,
        "created_at": datetime.now(timezone.utc)
    })


async def sync_doc_workflow_to_case(document_id: str, workflow_status: str, analyst: str = None, manager: str = None, comment: str = None, user_role: str = None, username: str = None):
    try:
        documents_col = get_collection("documents")
        doc_obj = await documents_col.find_one({"_id": ObjectId(document_id)})
        if doc_obj and doc_obj.get("case_id"):
            case_id = doc_obj["case_id"]
            cases_col = get_collection("cases")
            update_data = {"status": workflow_status, "updated_at": datetime.now(timezone.utc)}
            if analyst:
                update_data["assigned_analyst"] = analyst
            if manager:
                update_data["assigned_manager"] = manager
            await cases_col.update_one({"_id": ObjectId(case_id)}, {"$set": update_data})
            if comment and username and user_role:
                now = datetime.now(timezone.utc)
                if user_role == "Branch Manager":
                    await cases_col.update_one(
                        {"_id": ObjectId(case_id)},
                        {
                            "$push": {
                                "decisions": {
                                    "role": user_role,
                                    "action": workflow_status,
                                    "justification": comment,
                                    "performed_by": username,
                                    "timestamp": now
                                },
                                "audit_logs": {
                                    "action": f"CASE_{workflow_status}",
                                    "performed_by": username,
                                    "timestamp": now,
                                    "details": f"Decision updated via analysis sync: {comment}"
                                }
                            }
                        }
                    )
                else:
                    await cases_col.update_one(
                        {"_id": ObjectId(case_id)},
                        {
                            "$push": {
                                "notes": {
                                    "username": username,
                                    "role": user_role,
                                    "timestamp": now,
                                    "text": comment
                                },
                                "audit_logs": {
                                    "action": f"CASE_{workflow_status}",
                                    "performed_by": username,
                                    "timestamp": now,
                                    "details": f"Action sync: {comment}"
                                }
                            }
                        }
                    )
    except Exception as e:
        logger.warning(f"Failed to sync doc workflow to case: {e}")


# ------------------------------------------------------------------ #
#  POST /{document_id}/analyze — Trigger full pipeline
# ------------------------------------------------------------------ #
@router.post(
    "/{document_id}/analyze",
    response_model=AnalysisTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a full fraud analysis on a document",
)
async def trigger_analysis(
    document_id: str,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "System Admin"]))
):
    """
    Run the complete multi-stage fraud detection pipeline on a document:
    OCR → Metadata → Tampering → Signature → Amount → Anomaly → Risk → XAI
    """
    documents_col = get_collection("documents")
    analyses_col = get_collection("analyses")

    oid = _to_object_id(document_id, "document ID")

    # --- Fetch document ---
    doc = await documents_col.find_one({"_id": oid, "status": {"$ne": "deleted"}})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )

    # --- Wrap in Case and delegate to Case Analysis Pipeline ---
    try:
        case_id = doc.get("case_id")
        if not case_id:
            from app.models.case import create_case_dict
            cases_col = get_collection("cases")
            case_dict = create_case_dict(
                case_name=f"Case: {doc.get('original_filename', 'Doc')}",
                uploaded_by=current_user.get("username", "system"),
                branch=current_user.get("branch", "Canara Bank"),
                document_ids=[document_id],
            )
            case_res = await cases_col.insert_one(case_dict)
            case_id = str(case_res.inserted_id)
            await documents_col.update_one({"_id": oid}, {"$set": {"case_id": case_id}})
            
        from app.api.routes.cases import analyze_case_internal
        await analyze_case_internal(case_id, current_user.get("username", "system"))
        
        # Retrieve the updated analysis record for this document
        analysis_record = await analyses_col.find_one({"document_id": document_id})
        if analysis_record:
            analysis_id = str(analysis_record["_id"])
            await documents_col.update_one(
                {"_id": oid},
                {
                    "$set": {
                        "status": "flagged",
                        "latest_analysis_id": analysis_id,
                        "analyzed_at": datetime.now(timezone.utc),
                    }
                },
            )
            return AnalysisTriggerResponse(
                analysis_id=analysis_id,
                document_id=document_id,
                status="analyzed",
                processing_time_ms=analysis_record.get("processing_time_ms", 150.0),
                message="Analysis completed successfully via Case pipeline."
            )
    except Exception as e:
        logger.warning(f"Case analysis delegation failed: {e}. Falling back to single-document pipeline.")

    # --- Mark as processing atomically to prevent concurrent requests ---
    started_at = datetime.now(timezone.utc)
    result = await documents_col.update_one(
        {"_id": oid, "status": {"$ne": "processing"}},
        {"$set": {"status": "processing", "processing_started_at": started_at}},
    )
    if result.modified_count == 0:
        # Check if the document actually exists
        doc_check = await documents_col.find_one({"_id": oid, "status": {"$ne": "deleted"}})
        if not doc_check:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found.",
            )
        if doc_check.get("status") == "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This document is already being processed. Please wait.",
            )

    file_path = doc.get("storage_path", "")
    original_filename = doc.get("original_filename", doc.get("filename", ""))
    file_type = _determine_file_type(original_filename)
    t0 = time.perf_counter()

    # Partial results accumulator (stored even on failure)
    partial: dict = {}
    final_status = "failed"

    try:
        logger.info(f"Starting analysis pipeline for document {document_id}")

        # ---- a. Load document ----
        if file_type == "pdf":
            images = pdf_to_images(file_path)
            image = images[0] if images else None
        else:
            image = load_image(file_path)

        # ---- b. OCR ----
        logger.debug("Running OCR engine")
        ocr_engine = OCREngine()
        
        ocr_result = None
        for attempt in range(1, 4):
            try:
                logger.info(f"OCR Extraction attempt {attempt} for {file_path}")
                ocr_result = ocr_engine.process_document(file_path, file_type)
                # If it completed without raising an exception, it is a success (do not retry even if text is empty)
                logger.info(f"OCR Extraction attempt {attempt} completed.")
                break
            except Exception as e:
                logger.warning(f"OCR attempt {attempt} raised an exception: {e}")
                if attempt == 3:
                    raise e
        
        # Fallback handling: if ocr_result is None or extraction/full_text is empty, construct a low confidence/empty ocr_result
        if not ocr_result or not ocr_result.get("extraction", {}).get("full_text", "").strip():
            logger.warning("OCR Extraction returned empty/blank text. Constructing fallback low confidence OCR result.")
            if not ocr_result:
                ocr_result = {
                    "extraction": {
                        "full_text": "",
                        "blocks": [],
                        "avg_confidence": 0.0,
                        "word_count": 0,
                    },
                    "entities": ocr_engine.extract_entities(""),
                    "document_type": "Unknown",
                    "structured_data": {},
                    "field_confidences": {},
                    "ocr_confidence": 0.0,
                    "page_aware_fields": [],
                    "fields": [],
                    "file_path": file_path,
                    "file_type": file_type,
                }
            else:
                ocr_result["ocr_confidence"] = 0.0
                ocr_result["extraction"]["avg_confidence"] = 0.0
                ocr_result["structured_data"] = {}
                ocr_result["field_confidences"] = {}
                ocr_result["page_aware_fields"] = []
                ocr_result["fields"] = []
                
        # Run OCR Correction Layer before continuing
        try:
            from app.services.ocr_correction import OCRCorrectionLayer
            correction_layer = OCRCorrectionLayer()
            ocr_result = correction_layer.correct(ocr_result)
            
            # Re-extract entities on corrected text
            corrected_text = ocr_result.get("extraction", {}).get("full_text", "")
            if corrected_text:
                ocr_result["entities"] = ocr_engine.extract_entities(corrected_text)
        except Exception as e:
            logger.warning(f"OCR Correction Layer failed: {e}")
            
        partial["ocr"] = ocr_result
        
        # Log OCR extraction results for debugging
        extraction_data_raw = ocr_result.get("extraction", {})
        extracted_text = extraction_data_raw.get("full_text", "")
        extracted_entities = ocr_result.get("entities", {})
        entity_count = sum(len(v) for v in extracted_entities.values() if isinstance(v, list))
        logger.info(
            f"OCR completed: {len(extracted_text)} chars, "
            f"{len(extracted_text.split())} words, "
            f"{entity_count} entities extracted. "
            f"Preview: '{extracted_text[:200]}...'" if len(extracted_text) > 200 else f"Full text: '{extracted_text}'"
        )

        # ---- c. Metadata ----
        logger.debug("Running metadata extractor")
        meta_extractor = MetadataExtractor()
        metadata_result = meta_extractor.process(file_path, file_type)
        partial["metadata"] = metadata_result

        # ---- d. Tampering ----
        logger.debug("Running tampering detector")
        tampering_result = {}
        is_native_pdf = False
        if file_type == "pdf" and ocr_result:
            pages = ocr_result.get("extraction", {}).get("pages", [])
            if any(p.get("method") == "native" for p in pages):
                is_native_pdf = True

        # Loop through pages for image-based detection
        page_images = images if (file_type == "pdf" and 'images' in locals() and images) else ([image] if image is not None else [])

        tampering_anomalies = []
        tampering_heatmap_regions = []
        max_tampering_score = 0.0
        tampering_summaries = []
        
        tampering_result = {
            "ela": {"ela_score": 0.0, "suspicious_regions": []},
            "copy_move": {"detected": False, "regions": [], "confidence": 0.0},
            "noise": {"noise_score": 0.0, "inconsistent_blocks": 0},
            "edge": {"edge_score": 0.0, "suspicious_boundaries": 0},
            "composite_score": 0.0,
            "verdict": "clean",
            "anomalies": [],
            "summary": "No image available for tampering detection.",
            "heatmap_regions": [],
            "confidence": 100.0,
        }

        if is_native_pdf:
            tampering_result["summary"] = "Digital PDF document - image-level tampering analysis skipped to prevent false positives."
        elif page_images:
            tampering_detector = TamperingDetector()
            ela_scores = []
            copy_move_detected = False
            noise_scores = []
            edge_scores = []
            
            for idx, img_page in enumerate(page_images):
                p_num = idx + 1
                page_tamp = tampering_detector.process(img_page)
                # Capture ELA / Block scores
                ela_scores.append(page_tamp.get("ela", {}).get("ela_score", 0.0))
                if page_tamp.get("copy_move", {}).get("detected"):
                    copy_move_detected = True
                noise_scores.append(page_tamp.get("noise", {}).get("noise_score", 0.0))
                edge_scores.append(page_tamp.get("edge", {}).get("edge_score", 0.0))
                
                comp_score = page_tamp.get("composite_score", 0.0)
                if comp_score > max_tampering_score:
                    max_tampering_score = comp_score
                    tampering_result["verdict"] = page_tamp.get("verdict", "clean")
                
                # Propagate anomalies with page reference
                for anomaly in page_tamp.get("anomalies", []):
                    anomaly_copy = dict(anomaly)
                    anomaly_copy["page"] = p_num
                    if "evidence" not in anomaly_copy or not isinstance(anomaly_copy["evidence"], dict):
                        anomaly_copy["evidence"] = {}
                    anomaly_copy["evidence"]["page"] = p_num
                    tampering_anomalies.append(anomaly_copy)
                    
                # Propagate heatmap / suspicious regions
                for region in page_tamp.get("ela", {}).get("suspicious_regions", []):
                    region_copy = dict(region)
                    region_copy["page"] = p_num
                    tampering_heatmap_regions.append(region_copy)
                    
                for region in page_tamp.get("copy_move", {}).get("regions", []):
                    region_copy = dict(region)
                    region_copy["page"] = p_num
                    tampering_heatmap_regions.append(region_copy)
                    
                if page_tamp.get("summary"):
                    tampering_summaries.append(f"Page {p_num}: {page_tamp.get('summary')}")
            
            # Combine aggregated fields
            tampering_result["composite_score"] = round(max_tampering_score, 2)
            tampering_result["anomalies"] = tampering_anomalies
            tampering_result["ela"] = {
                "ela_score": round(max(ela_scores) if ela_scores else 0.0, 2),
                "suspicious_regions": [r for r in tampering_heatmap_regions if "intensity" in r]
            }
            tampering_result["copy_move"] = {
                "detected": copy_move_detected,
                "regions": [r for r in tampering_heatmap_regions if "intensity" not in r],
                "confidence": 95.0 if copy_move_detected else 0.0
            }
            tampering_result["summary"] = " | ".join(tampering_summaries) if tampering_summaries else "All pages clean."
            tampering_result["heatmap_regions"] = tampering_heatmap_regions
            
        partial["tampering"] = tampering_result

        # ---- e. Signature ----
        logger.debug("Running signature verifier")
        signature_anomalies = []
        signature_locations = []
        max_sig_risk_score = 0.0
        sig_summaries = []
        total_signatures_found = 0
        
        signature_result = {
            "signatures_found": 0,
            "signature_locations": [],
            "consistency": "n/a",
            "risk_score": 0.0,
            "anomalies": [],
            "summary": "No image available for signature verification.",
            "confidence": 100.0
        }

        if page_images:
            sig_verifier = SignatureVerifier()
            for idx, img_page in enumerate(page_images):
                p_num = idx + 1
                page_sig = sig_verifier.process(img_page)
                total_signatures_found += page_sig.get("signatures_found", 0)
                
                sig_score = page_sig.get("risk_score", 0.0)
                if sig_score > max_sig_risk_score:
                    max_sig_risk_score = sig_score
                    signature_result["consistency"] = page_sig.get("consistency", "n/a")
                
                # Propagate anomalies with page reference
                for anomaly in page_sig.get("anomalies", []):
                    anomaly_copy = dict(anomaly)
                    anomaly_copy["page"] = p_num
                    if "evidence" not in anomaly_copy or not isinstance(anomaly_copy["evidence"], dict):
                        anomaly_copy["evidence"] = {}
                    anomaly_copy["evidence"]["page"] = p_num
                    signature_anomalies.append(anomaly_copy)
                    
                # Propagate signature locations
                for loc in page_sig.get("signature_locations", []):
                    loc_copy = dict(loc)
                    loc_copy["page"] = p_num
                    signature_locations.append(loc_copy)
                    
                if page_sig.get("summary"):
                    sig_summaries.append(f"Page {p_num}: {page_sig.get('summary')}")
            
            signature_result["signatures_found"] = total_signatures_found
            signature_result["signature_locations"] = signature_locations
            signature_result["risk_score"] = round(max_sig_risk_score, 2)
            signature_result["anomalies"] = signature_anomalies
            signature_result["summary"] = " | ".join(sig_summaries) if sig_summaries else "No signatures found."
            
        partial["signature"] = signature_result

        # ---- f. Amount ----
        logger.debug("Running amount detector")
        amount_detector = AmountDetector()
        extraction_data = ocr_result.get("extraction", {})
        full_text = extraction_data.get("full_text", "")
        structured_data = ocr_result.get("structured_data", {})
        amount_result = amount_detector.process(full_text, structured_data)
        partial["amount"] = amount_result

        # ---- g. Anomaly detection ----
        logger.debug("Running anomaly detector")
        anomaly_detector = AnomalyDetector()
        entities = ocr_result.get("entities", {})
        
        # Fetch recent analyses for cross-document validation (demo/MVP logic)
        try:
            recent_analyses_cursor = analyses_col.find(
                {"document_id": {"$ne": document_id}, "status": "analyzed"}
            ).sort("completed_at", -1).limit(5)
            
            recent_analyses = await recent_analyses_cursor.to_list(length=5)
            past_entities_list = [ra.get("results", {}).get("ocr", {}).get("entities", {}) for ra in recent_analyses if ra.get("results", {}).get("ocr")]
        except Exception as e:
            logger.warning(f"Could not fetch recent analyses for cross-document validation: {e}")
            past_entities_list = []
            
        anomaly_result = anomaly_detector.process(ocr_result, metadata_result, entities, past_entities_list)
        partial["anomaly"] = anomaly_result

        # ---- h. Risk scoring ----
        logger.debug("Running risk scorer")
        risk_scorer = RiskScorer()
        risk_result = risk_scorer.process(
            ocr_result, metadata_result, tampering_result, signature_result,
            amount_result, anomaly_result,
        )
        partial["risk_score"] = risk_result

        # ---- i. Explainable AI ----
        logger.debug("Running explainable AI")
        xai = ExplainableAI()
        explanation = xai.generate_explanation(
            risk_result, metadata_result, tampering_result,
            signature_result, amount_result, anomaly_result,
        )
        partial["explanation"] = explanation

        final_status = "analyzed"
        logger.info(
            f"Analysis pipeline completed for {document_id} — "
            f"risk: {risk_result.get('composite', 0):.1f}, "
            f"tier: {risk_result.get('tier', 'unknown')}"
        )

    except Exception as exc:
        logger.error(f"Analysis pipeline failed for {document_id}: {exc}")
        partial["error"] = str(exc)
        final_status = "failed"

    # --- Timing ---
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    partial["processing_time_ms"] = elapsed_ms

    # --- Persist analysis ---
    def sanitize_for_mongo(obj):
        import numpy as np
        if isinstance(obj, dict):
            return {k: sanitize_for_mongo(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sanitize_for_mongo(v) for v in obj]
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)):
            return int(obj)
        elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return sanitize_for_mongo(obj.tolist())
        return obj

    # Expose workflow and highlight_regions in the analysis_dict
    risk_result_data = partial.get("risk_score", {})
    workflow_data = risk_result_data.get("workflow", {
        "status": "UNASSIGNED",
        "assigned_analyst": None,
        "assigned_manager": None,
        "priority": "LOW",
        "escalation_reason": None,
        "escalated_by": None
    })
    highlight_regions = risk_result_data.get("highlight_regions", [])

    analysis_dict = create_analysis_dict(
        document_id=document_id,
        status=final_status,
        results=sanitize_for_mongo(partial),
        processing_time_ms=elapsed_ms,
    )
    analysis_dict["workflow"] = workflow_data
    analysis_dict["highlight_regions"] = highlight_regions
    analysis_dict["version"] = 1
    
    # Standardized audit log entries
    initial_audit_logs = [
        {
            "timestamp": datetime.now(timezone.utc),
            "user": doc.get("uploaded_by", "system"),
            "role": "Underwriting Officer" if doc.get("uploaded_by") != "system" else "System Admin",
            "action": "UPLOAD_DOCUMENT",
            "details": f"Uploaded document. Priority initialized as {workflow_data.get('priority')}.",
            "analysis_id": ""
        }
    ]
    if final_status == "analyzed":
        initial_audit_logs.append({
            "timestamp": datetime.now(timezone.utc),
            "user": "System Pipeline",
            "role": "System Admin",
            "action": "COMPLETED_ANALYSIS",
            "details": f"Analysis complete. Composite risk score: {risk_result_data.get('composite', 0)}%. Workflow status: {workflow_data.get('status')}.",
            "analysis_id": ""
        })
    else:
        initial_audit_logs.append({
            "timestamp": datetime.now(timezone.utc),
            "user": "System Pipeline",
            "role": "System Admin",
            "action": "FAILED_ANALYSIS",
            "details": f"Analysis failed: {partial.get('error', 'Unknown error')}",
            "analysis_id": ""
        })
    analysis_dict["audit_logs"] = initial_audit_logs

    # Delete any existing analysis for this document to avoid DuplicateKeyError
    await analyses_col.delete_many({"document_id": document_id})

    insert_result = await analyses_col.insert_one(analysis_dict)
    analysis_id = str(insert_result.inserted_id)

    # Set analysis_id in the audit logs
    for log in initial_audit_logs:
        log["analysis_id"] = analysis_id
    await analyses_col.update_one({"_id": insert_result.inserted_id}, {"$set": {"audit_logs": initial_audit_logs}})

    # --- Update document status (never auto-approved after upload) ---
    await documents_col.update_one(
        {"_id": oid},
        {
            "$set": {
                "status": "flagged",
                "latest_analysis_id": analysis_id,
                "analyzed_at": datetime.now(timezone.utc),
            }
        },
    )

    if final_status == "failed":
        logger.warning(f"Document {document_id} marked as failed")

    return AnalysisTriggerResponse(
        analysis_id=analysis_id,
        document_id=document_id,
        status=final_status,
        processing_time_ms=elapsed_ms,
        message=(
            "Analysis completed successfully."
            if final_status == "analyzed"
            else f"Analysis failed: {partial.get('error', 'Unknown error')}"
        ),
    )


# ------------------------------------------------------------------ #
#  GET /{analysis_id} — Full analysis result
# ------------------------------------------------------------------ #
@router.get(
    "/{analysis_id}",
    response_model=AnalysisResponse,
    summary="Get full analysis result",
)
async def get_analysis(
    analysis_id: str,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Retrieve the complete analysis result by analysis ID."""
    analyses_col = get_collection("analyses")
    oid = _to_object_id(analysis_id, "analysis ID")

    doc = await analyses_col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found.",
        )

    if current_user.get("role") == "Branch Manager":
        if doc.get("workflow", {}).get("status") not in ("ESCALATED", "APPROVED", "REJECTED", "CLOSED"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. This case has not been escalated to the Branch Manager yet.",
            )

    return AnalysisResponse(**serialize_analysis(doc))


# ------------------------------------------------------------------ #
#  GET /document/{document_id} — Latest analysis for a document
# ------------------------------------------------------------------ #
@router.get(
    "/document/{document_id}",
    response_model=AnalysisResponse,
    summary="Get the latest analysis for a document",
)
async def get_analysis_by_document(
    document_id: str,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Find the most recent analysis associated with a given document."""
    analyses_col = get_collection("analyses")

    doc = await analyses_col.find_one(
        {"document_id": document_id},
        sort=[("created_at", -1)],
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No analysis found for document {document_id}.",
        )

    if current_user.get("role") == "Branch Manager":
        if doc.get("workflow", {}).get("status") not in ("ESCALATED", "APPROVED", "REJECTED", "CLOSED"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. This case has not been escalated to the Branch Manager yet.",
            )

    return AnalysisResponse(**serialize_analysis(doc))


# ------------------------------------------------------------------ #
#  GET /{analysis_id}/anomalies — Anomalies only
# ------------------------------------------------------------------ #
@router.get(
    "/{analysis_id}/anomalies",
    summary="Get anomalies from an analysis",
)
async def get_anomalies(
    analysis_id: str,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Return just the anomalies section of an analysis."""
    analyses_col = get_collection("analyses")
    oid = _to_object_id(analysis_id, "analysis ID")

    doc = await analyses_col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found.",
        )

    results = doc.get("results", {})
    anomaly_data = results.get("anomaly", {})

    # Flatten all anomaly lists
    all_anomalies: list[dict] = []
    for key in ("text_anomalies", "cross_field_anomalies", "pattern_anomalies"):
        all_anomalies.extend(anomaly_data.get(key, []))

    # Include anomalies from other modules
    for module in ("metadata", "tampering", "signature", "amount"):
        module_data = results.get(module, {})
        all_anomalies.extend(module_data.get("anomalies", []))

    return {
        "analysis_id": analysis_id,
        "total_anomalies": len(all_anomalies),
        "anomalies": all_anomalies,
        "anomaly_risk_score": anomaly_data.get("risk_score", 0),
    }


# ------------------------------------------------------------------ #
#  GET /{analysis_id}/risk-score — Risk score breakdown
# ------------------------------------------------------------------ #
@router.get(
    "/{analysis_id}/risk-score",
    summary="Get risk score breakdown",
)
async def get_risk_score(
    analysis_id: str,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Return the risk score breakdown of an analysis."""
    analyses_col = get_collection("analyses")
    oid = _to_object_id(analysis_id, "analysis ID")

    doc = await analyses_col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found.",
        )

    risk_data = doc.get("results", {}).get("risk_score", {})
    return {
        "analysis_id": analysis_id,
        **risk_data,
    }


# ------------------------------------------------------------------ #
#  GET /{analysis_id}/explanation — XAI explanation
# ------------------------------------------------------------------ #
@router.get(
    "/{analysis_id}/explanation",
    summary="Get explainable AI output",
)
async def get_explanation(
    analysis_id: str,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    """Return the human-readable explanation of an analysis."""
    analyses_col = get_collection("analyses")
    oid = _to_object_id(analysis_id, "analysis ID")

    doc = await analyses_col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found.",
        )

    explanation = doc.get("results", {}).get("explanation", {})
    return {
        "analysis_id": analysis_id,
        **explanation,
    }


# ------------------------------------------------------------------ #
#  POST /{analysis_id}/notes — Add internal note
# ------------------------------------------------------------------ #
from pydantic import BaseModel

class NoteRequest(BaseModel):
    note: str

@router.post(
    "/{analysis_id}/notes",
    summary="Add an internal note to an analysis case",
)
async def add_case_note(
    analysis_id: str,
    payload: NoteRequest,
    current_user: dict = Depends(RoleChecker(["Underwriting Officer", "Fraud Analyst", "Branch Manager", "Compliance Auditor", "System Admin"]))
):
    analyses_col = get_collection("analyses")
    oid = _to_object_id(analysis_id, "analysis ID")
    
    analysis_doc = await analyses_col.find_one({"_id": oid})
    if not analysis_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found.",
        )
        
    current_status = analysis_doc.get("workflow", {}).get("status", "UNASSIGNED")
    if current_status in ("APPROVED", "REJECTED") and current_user["role"] not in ("Branch Manager", "System Admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add notes to a finalized case."
        )

    if current_user.get("role") == "Branch Manager":
        if current_status not in ("ESCALATED", "APPROVED", "REJECTED", "CLOSED"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Case has not been escalated to the Branch Manager yet.",
            )
        
    new_version = analysis_doc.get("version", 1) + 1
    now = datetime.now(timezone.utc)
    
    note_entry = {
        "username": current_user["username"],
        "role": current_user["role"],
        "timestamp": now,
        "note": payload.note
    }
    
    # Standardized audit log
    audit_entry = {
        "timestamp": now,
        "user": current_user["username"],
        "role": current_user["role"],
        "action": "NOTE_ADDED",
        "details": f"Added note: {payload.note[:100]}...",
        "analysis_id": analysis_id
    }
    
    await analyses_col.update_one(
        {"_id": oid},
        {
            "$push": {
                "notes": note_entry,
                "audit_logs": audit_entry
            },
            "$set": {
                "version": new_version,
                "updated_at": now
            }
        }
    )
    
    # Write to compliance audit log
    try:
        audit_col = get_collection("audit_logs")
        await audit_col.insert_one({
            "timestamp": now,
            "user_id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "action": "add_case_note",
            "details": {
                "analysis_id": analysis_id,
                "note_preview": payload.note[:100]
            }
        })
    except Exception:
        pass
        
    return {"status": "success", "message": "Note added successfully", "note": note_entry, "version": new_version}


# ------------------------------------------------------------------ #
#  POST /{analysis_id}/assign — Assign analyst with locking
# ------------------------------------------------------------------ #
class AssignRequest(BaseModel):
    analyst_username: Optional[str] = None
    note: Optional[str] = None

@router.post(
    "/{analysis_id}/assign",
    summary="Assign a case to an analyst",
)
async def assign_case(
    analysis_id: str,
    payload: Optional[AssignRequest] = None,
    current_user: dict = Depends(RoleChecker(["Fraud Analyst", "Branch Manager", "System Admin"]))
):
    analyses_col = get_collection("analyses")
    oid = _to_object_id(analysis_id, "analysis ID")
    analysis_doc = await analyses_col.find_one({"_id": oid})
    if not analysis_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found."
        )
    
    # Check strict transition state
    current_status = analysis_doc.get("workflow", {}).get("status", "UNASSIGNED")
    if current_status in ("APPROVED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot assign a case that is already {current_status}."
        )
        
    assigned_analyst = analysis_doc.get("workflow", {}).get("assigned_analyst")
    
    # Analyst Assignment Locking
    target_analyst = (payload.analyst_username if payload else None) or current_user["username"]
    
    if assigned_analyst and assigned_analyst != target_analyst:
        if current_user["role"] not in ("Branch Manager", "System Admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Case is locked and currently assigned to {assigned_analyst}. Only a manager or admin can override."
            )

    new_version = analysis_doc.get("version", 1) + 1
    now = datetime.now(timezone.utc)
    
    # Standardized audit log
    audit_entry = {
        "timestamp": now,
        "user": current_user["username"],
        "role": current_user["role"],
        "action": "ESCALATED_CASE",
        "details": f"Assigned to {target_analyst} and escalated to manager",
        "analysis_id": analysis_id
    }
    
    custom_note = payload.note.strip() if (payload and payload.note) else ""
    note_text = f"Case assigned to {target_analyst} and escalated to manager (Version {new_version})."
    if custom_note:
        note_text += f" Analyst Note: {custom_note}"

    await analyses_col.update_one(
        {"_id": oid},
        {
            "$set": {
                "workflow.status": "ESCALATED",
                "workflow.assigned_analyst": target_analyst,
                "workflow.escalated_by": target_analyst,
                "workflow.assigned_manager": "Branch Manager",
                "workflow.escalation_timestamp": now.isoformat(),
                "workflow.escalation_reason": custom_note or "Assigned and escalated to manager",
                "version": new_version,
                "updated_at": now
            },
            "$push": {
                "audit_logs": audit_entry,
                "notes": {
                    "username": current_user["username"],
                    "role": current_user["role"],
                    "timestamp": now,
                    "note": note_text
                }
            }
        }
    )
    
    # Sync status to documents collection for backward compatibility
    doc = None
    try:
        doc_oid = ObjectId(analysis_doc["document_id"])
        documents_col = get_collection("documents")
        doc = await documents_col.find_one({"_id": doc_oid})
        await documents_col.update_one({"_id": doc_oid}, {"$set": {"status": "escalated"}})
        
        # Sync case status
        await sync_doc_workflow_to_case(
            document_id=analysis_doc["document_id"],
            workflow_status="ESCALATED",
            analyst=target_analyst,
            comment=custom_note or "Assigned and escalated",
            user_role=current_user["role"],
            username=current_user["username"]
        )
    except Exception:
        pass

    # Notify the Underwriter
    if doc:
        underwriter = doc.get("uploaded_by") or "system"
        filename = doc.get("original_filename") or doc.get("filename", "document")
        try:
            await create_notification(
                db=analyses_col.database,
                recipient_username=underwriter,
                document_id=analysis_doc["document_id"],
                document_name=filename,
                message=f"Document '{filename}' was escalated to the manager by analyst {target_analyst}. Note: {custom_note or 'Assigned and escalated'}",
                type="escalated"
            )
        except Exception as e:
            logger.error(f"Failed to create escalation notification: {e}")
        
    # Write to compliance audit log
    try:
        audit_col = get_collection("audit_logs")
        await audit_col.insert_one({
            "timestamp": now,
            "user_id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "action": "assignment",
            "details": {
                "analysis_id": analysis_id,
                "document_id": analysis_doc.get("document_id"),
                "assigned_to": target_analyst
            }
        })
    except Exception:
        pass
    
    return {"status": "success", "message": f"Case escalated to manager and assigned to {target_analyst} successfully", "version": new_version}


# ------------------------------------------------------------------ #
#  POST /{analysis_id}/escalate — Escalate case to manager
# ------------------------------------------------------------------ #
class EscalateRequest(BaseModel):
    reason: str
    manager_username: Optional[str] = None

@router.post(
    "/{analysis_id}/escalate",
    summary="Escalate a case to a manager",
)
async def escalate_case(
    analysis_id: str,
    payload: EscalateRequest,
    current_user: dict = Depends(RoleChecker(["Fraud Analyst", "System Admin"]))
):
    analyses_col = get_collection("analyses")
    oid = _to_object_id(analysis_id, "analysis ID")
    analysis_doc = await analyses_col.find_one({"_id": oid})
    if not analysis_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found."
        )
    
    current_status = analysis_doc.get("workflow", {}).get("status", "UNASSIGNED")
    if current_status in ("APPROVED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot escalate a case that is already {current_status}."
        )
        
    # Escalation Validation
    workflow_data = analysis_doc.get("workflow", {})
    if not workflow_data.get("assigned_analyst"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot escalate: Case must be assigned to an analyst first."
        )
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot escalate: Escalation reason is required."
        )
    
    risk_score = analysis_doc.get("risk_score", {})
    if risk_score.get("composite") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot escalate: Fraud score is not calculated."
        )
        
    if current_status == "ESCALATED":
        return {"status": "success", "message": "Case escalated to manager successfully", "version": analysis_doc.get("version", 1)}

    if current_status != "UNDER_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot escalate: Case must be in UNDER_REVIEW status."
        )

    new_version = analysis_doc.get("version", 1) + 1
    now = datetime.now(timezone.utc)
    
    # Standardized audit log
    audit_entry = {
        "timestamp": now,
        "user": current_user["username"],
        "role": current_user["role"],
        "action": "ESCALATED_CASE",
        "details": payload.reason,
        "analysis_id": analysis_id
    }
    
    await analyses_col.update_one(
        {"_id": oid},
        {
            "$set": {
                "workflow.status": "ESCALATED",
                "workflow.escalation_reason": payload.reason,
                "workflow.escalated_by": current_user["username"],
                "workflow.assigned_manager": payload.manager_username or "Branch Manager",
                "workflow.escalation_timestamp": now.isoformat(),
                "version": new_version,
                "updated_at": now
            },
            "$push": {
                "audit_logs": audit_entry,
                "notes": {
                    "username": current_user["username"],
                    "role": current_user["role"],
                    "timestamp": now,
                    "note": f"Escalated case to manager. Reason: {payload.reason} (Version {new_version})."
                }
            }
        }
    )
    
    doc = None
    try:
        doc_oid = ObjectId(analysis_doc["document_id"])
        documents_col = get_collection("documents")
        doc = await documents_col.find_one({"_id": doc_oid})
        await documents_col.update_one({"_id": doc_oid}, {"$set": {"status": "escalated"}})
        
        # Sync case status
        await sync_doc_workflow_to_case(
            document_id=analysis_doc["document_id"],
            workflow_status="ESCALATED",
            comment=payload.reason,
            user_role=current_user["role"],
            username=current_user["username"]
        )
    except Exception:
        pass

    # Notify the Underwriter
    if doc:
        underwriter = doc.get("uploaded_by") or "system"
        filename = doc.get("original_filename") or doc.get("filename", "document")
        try:
            await create_notification(
                db=analyses_col.database,
                recipient_username=underwriter,
                document_id=analysis_doc["document_id"],
                document_name=filename,
                message=f"Document '{filename}' was escalated to the manager by analyst {current_user['username']}. Reason: {payload.reason}",
                type="escalated"
            )
        except Exception as e:
            logger.warning(f"Failed to create escalation notification: {e}")
        
    # Write to compliance audit log
    try:
        audit_col = get_collection("audit_logs")
        await audit_col.insert_one({
            "timestamp": now,
            "user_id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "action": "escalation",
            "details": {
                "analysis_id": analysis_id,
                "document_id": analysis_doc.get("document_id"),
                "reason": payload.reason
            }
        })
    except Exception:
        pass
    
    return {"status": "success", "message": "Case escalated to manager successfully", "version": new_version}


# ------------------------------------------------------------------ #
#  POST /{analysis_id}/safe — Mark case as safe / close case
# ------------------------------------------------------------------ #
class SafeRequest(BaseModel):
    comment: str

@router.post(
    "/{analysis_id}/safe",
    summary="Mark case as safe to process / close investigation",
)
async def mark_case_safe(
    analysis_id: str,
    payload: SafeRequest,
    current_user: dict = Depends(RoleChecker(["Fraud Analyst", "System Admin"]))
):
    analyses_col = get_collection("analyses")
    documents_col = get_collection("documents")
    oid = _to_object_id(analysis_id, "analysis ID")
    
    analysis_doc = await analyses_col.find_one({"_id": oid})
    if not analysis_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found."
        )
        
    current_status = analysis_doc.get("workflow", {}).get("status", "UNASSIGNED")
    if current_status in ("APPROVED", "REJECTED", "SAFE_TO_PROCESS"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot close a case that is already {current_status}."
        )
        
    assigned_analyst = analysis_doc.get("workflow", {}).get("assigned_analyst")
    if not assigned_analyst:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot close case: Case must be assigned to an analyst first."
        )
        
    if assigned_analyst != current_user["username"] and current_user["role"] != "System Admin":
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned analyst or admin can close this case."
        )

    new_version = analysis_doc.get("version", 1) + 1
    now = datetime.now(timezone.utc)
    
    # Standardized audit log
    audit_entry = {
        "timestamp": now,
        "user": current_user["username"],
        "role": current_user["role"],
        "action": "CLOSED_CASE",
        "details": f"Marked safe: {payload.comment}",
        "analysis_id": analysis_id
    }
    
    await analyses_col.update_one(
        {"_id": oid},
        {
            "$set": {
                "workflow.status": "SAFE_TO_PROCESS",
                "version": new_version,
                "updated_at": now
            },
            "$push": {
                "audit_logs": audit_entry,
                "notes": {
                    "username": current_user["username"],
                    "role": current_user["role"],
                    "timestamp": now,
                    "note": f"Investigation closed. Marked safe: {payload.comment} (Version {new_version})."
                }
            }
        }
    )
    
    try:
        doc_oid = ObjectId(analysis_doc["document_id"])
        await documents_col.update_one({"_id": doc_oid}, {"$set": {"status": "approved"}})
        
        # Sync case status
        await sync_doc_workflow_to_case(
            document_id=analysis_doc["document_id"],
            workflow_status="APPROVED",
            comment=payload.comment,
            user_role=current_user["role"],
            username=current_user["username"]
        )
    except Exception:
        pass
        
    # Write to compliance audit log
    try:
        audit_col = get_collection("audit_logs")
        await audit_col.insert_one({
            "timestamp": now,
            "user_id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "action": "decision_approve",  # Analyst resolved safe counts as compliance approval entry
            "details": {
                "analysis_id": analysis_id,
                "document_id": analysis_doc.get("document_id"),
                "comment": payload.comment
            }
        })
    except Exception:
        pass
        
    return {"status": "success", "message": "Case marked safe successfully", "version": new_version}


@router.post(
    "/{analysis_id}/reject",
    summary="Directly reject a case by a Fraud Analyst",
)
async def reject_analysis_case(
    analysis_id: str,
    payload: SafeRequest,
    current_user: dict = Depends(RoleChecker(["Fraud Analyst", "System Admin"]))
):
    analyses_col = get_collection("analyses")
    documents_col = get_collection("documents")
    oid = _to_object_id(analysis_id, "analysis ID")
    
    analysis_doc = await analyses_col.find_one({"_id": oid})
    if not analysis_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found."
        )
        
    current_status = analysis_doc.get("workflow", {}).get("status", "UNASSIGNED")
    if current_status in ("APPROVED", "REJECTED", "SAFE_TO_PROCESS"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject a case that is already {current_status}."
        )
        
    assigned_analyst = analysis_doc.get("workflow", {}).get("assigned_analyst")
    if not assigned_analyst:
        assigned_analyst = current_user["username"]
    elif assigned_analyst != current_user["username"] and current_user["role"] != "System Admin":
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned analyst or admin can reject this case."
        )

    if not payload.comment or not payload.comment.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Justification/comment is required to reject a case."
        )

    new_version = analysis_doc.get("version", 1) + 1
    now = datetime.now(timezone.utc)
    
    audit_entry = {
        "timestamp": now,
        "user": current_user["username"],
        "role": current_user["role"],
        "action": "REJECTED_CASE",
        "details": f"Rejected by analyst: {payload.comment}",
        "analysis_id": analysis_id
    }
    
    await analyses_col.update_one(
        {"_id": oid},
        {
            "$set": {
                "workflow.status": "REJECTED",
                "workflow.assigned_analyst": assigned_analyst,
                "version": new_version,
                "updated_at": now
            },
            "$push": {
                "audit_logs": audit_entry,
                "notes": {
                    "username": current_user["username"],
                    "role": current_user["role"],
                    "timestamp": now,
                    "note": f"Investigation closed. Rejected by analyst: {payload.comment} (Version {new_version})."
                }
            }
        }
    )
    
    doc = None
    try:
        doc_oid = ObjectId(analysis_doc["document_id"])
        doc = await documents_col.find_one({"_id": doc_oid})
        await documents_col.update_one({"_id": doc_oid}, {"$set": {"status": "rejected"}})
        
        # Sync case status
        await sync_doc_workflow_to_case(
            document_id=analysis_doc["document_id"],
            workflow_status="REJECTED",
            comment=payload.comment,
            user_role=current_user["role"],
            username=current_user["username"]
        )
    except Exception:
        pass

    # Notify the Underwriter
    if doc:
        underwriter = doc.get("uploaded_by") or "system"
        filename = doc.get("original_filename") or doc.get("filename", "document")
        try:
            await create_notification(
                db=analyses_col.database,
                recipient_username=underwriter,
                document_id=analysis_doc["document_id"],
                document_name=filename,
                message=f"Document '{filename}' was rejected by fraud analyst {current_user['username']}. Comment: {payload.comment}",
                type="rejected"
            )
        except Exception as e:
            logger.warning(f"Failed to create rejection notification: {e}")
        
    # Write to compliance audit log
    try:
        audit_col = get_collection("audit_logs")
        await audit_col.insert_one({
            "timestamp": now,
            "user_id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "action": "decision_reject",
            "details": {
                "analysis_id": analysis_id,
                "document_id": analysis_doc.get("document_id"),
                "comment": payload.comment
            }
        })
    except Exception:
        pass
        
    return {"status": "success", "message": "Case rejected successfully", "version": new_version}


# ------------------------------------------------------------------ #
#  POST /{analysis_id}/priority — Set priority
# ------------------------------------------------------------------ #
class PriorityRequest(BaseModel):
    priority: str

@router.post(
    "/{analysis_id}/priority",
    summary="Update the priority level of a case",
)
async def update_priority(
    analysis_id: str,
    payload: PriorityRequest,
    current_user: dict = Depends(RoleChecker(["Fraud Analyst", "Branch Manager", "System Admin"]))
):
    if payload.priority not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Priority must be one of: LOW, MEDIUM, HIGH, CRITICAL"
        )
        
    analyses_col = get_collection("analyses")
    oid = _to_object_id(analysis_id, "analysis ID")
    analysis_doc = await analyses_col.find_one({"_id": oid})
    if not analysis_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found."
        )
        
    current_status = analysis_doc.get("workflow", {}).get("status", "UNASSIGNED")
    if current_status in ("APPROVED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change priority on a case that is already {current_status}."
        )
        
    new_version = analysis_doc.get("version", 1) + 1
    now = datetime.now(timezone.utc)
    old_priority = analysis_doc.get("workflow", {}).get("priority", "LOW")
    
    # Standardized audit log
    audit_entry = {
        "timestamp": now,
        "user": current_user["username"],
        "role": current_user["role"],
        "action": "PRIORITY_CHANGED",
        "details": f"Priority updated from {old_priority} to {payload.priority}",
        "analysis_id": analysis_id
    }
    
    await analyses_col.update_one(
        {"_id": oid},
        {
            "$set": {
                "workflow.priority": payload.priority,
                "version": new_version,
                "updated_at": now
            },
            "$push": {
                "audit_logs": audit_entry,
                "notes": {
                    "username": current_user["username"],
                    "role": current_user["role"],
                    "timestamp": now,
                    "note": f"Priority changed from {old_priority} to {payload.priority} (Version {new_version})."
                }
            }
        }
    )
    
    # Write to compliance audit log
    try:
        audit_col = get_collection("audit_logs")
        await audit_col.insert_one({
            "timestamp": now,
            "user_id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "action": "priority_change",
            "details": {
                "analysis_id": analysis_id,
                "document_id": analysis_doc.get("document_id"),
                "old_priority": old_priority,
                "new_priority": payload.priority
            }
        })
    except Exception:
        pass
        
    return {"status": "success", "message": f"Priority changed to {payload.priority} successfully", "version": new_version}


# ------------------------------------------------------------------ #
#  POST /{analysis_id}/decide — Make decision
# ------------------------------------------------------------------ #
class DecisionRequest(BaseModel):
    decision: str  # "approve" | "reject" | "escalate" | "waitlist"
    comment: str
    explicit_confirmation: Optional[bool] = False

@router.post(
    "/{analysis_id}/decide",
    summary="Submit an underwriter or manager decision for a document case",
)
async def submit_decision(
    analysis_id: str,
    payload: DecisionRequest,
    current_user: dict = Depends(RoleChecker(["Branch Manager", "System Admin"]))
):
    if payload.decision not in ("approve", "reject", "escalate", "waitlist"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be one of: approve, reject, escalate, waitlist"
        )
        
    analyses_col = get_collection("analyses")
    documents_col = get_collection("documents")
    oid = _to_object_id(analysis_id, "analysis ID")
    
    analysis_doc = await analyses_col.find_one({"_id": oid})
    if not analysis_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found.",
        )
        
    doc_oid = ObjectId(analysis_doc["document_id"])
    
    # Check transitions consistency
    current_status = analysis_doc.get("workflow", {}).get("status", "UNASSIGNED")
    if current_status in ("APPROVED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change state of a finalized case (already {current_status})."
        )
        
    if current_status != "ESCALATED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot submit decision: Manager final reviews are restricted to ESCALATED cases only."
        )

    if not payload.comment or not payload.comment.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A comment/justification is required for all manager decisions."
        )
        
    if payload.decision == "escalate":
        workflow_data = analysis_doc.get("workflow", {})
        if not workflow_data.get("assigned_analyst"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot escalate: Case must be assigned to an analyst first."
            )
        if not payload.comment or not payload.comment.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot escalate: Escalation reason/comment is required."
            )
        risk_score = analysis_doc.get("risk_score", {})
        if risk_score.get("composite") is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot escalate: Fraud score is not calculated."
            )
        if current_status != "UNDER_REVIEW":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot escalate: Case must be in UNDER_REVIEW status."
            )

    # Manager Decision Safety Rules
    priority = analysis_doc.get("workflow", {}).get("priority", "LOW")
    if payload.decision == "approve" and priority == "CRITICAL":
        if not payload.explicit_confirmation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Explicit confirmation is required to approve a CRITICAL priority case."
            )
        if not payload.comment or len(payload.comment.strip()) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A detailed override justification (at least 10 characters) is required to approve a CRITICAL priority case."
            )
        notes = analysis_doc.get("notes", [])
        analyst_notes = [n for n in notes if n.get("role") == "Fraud Analyst"]
        if not analyst_notes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot approve a CRITICAL priority case without existing analyst notes."
            )
            
    # Map decision to document and display status
    status_map = {
      "approve": ("VERIFIED", "approved", "APPROVED"),
      "reject": ("REJECTED", "rejected", "REJECTED"),
      "escalate": ("UNDER REVIEW", "escalated", "ESCALATED"),
      "waitlist": ("WAITLISTED", "flagged", "CLOSED")
    }
    xai_status, doc_status, workflow_status = status_map[payload.decision]
    
    new_version = analysis_doc.get("version", 1) + 1
    now = datetime.now(timezone.utc)
    
    decision_entry = {
        "username": current_user["username"],
        "role": current_user["role"],
        "timestamp": now,
        "decision": payload.decision,
        "comment": payload.comment
    }
    
    # Standardized audit log
    action_map = {
        "approve": "APPROVED_CASE",
        "reject": "REJECTED_CASE",
        "escalate": "ESCALATED_CASE",
        "waitlist": "WAITLISTED_CASE"
    }
    audit_entry = {
        "timestamp": now,
        "user": current_user["username"],
        "role": current_user["role"],
        "action": action_map[payload.decision],
        "details": payload.comment if payload.decision != "escalate" else f"Escalated to manager: {payload.comment}",
        "analysis_id": analysis_id
    }
    
    update_fields = {
        "results.explanation.document_status": xai_status,
        "workflow.status": workflow_status,
        "version": new_version,
        "updated_at": now
    }
    if payload.decision == "escalate":
        update_fields["workflow.escalation_reason"] = payload.comment
        update_fields["workflow.escalated_by"] = current_user["username"]
        update_fields["workflow.assigned_manager"] = "Branch Manager"
    elif payload.decision == "waitlist":
        update_fields["workflow.waitlist_reason"] = payload.comment
        update_fields["workflow.waitlisted_by"] = current_user["username"]
        update_fields["workflow.waitlist_timestamp"] = now.isoformat()
        
    await analyses_col.update_one(
        {"_id": oid},
        {
            "$set": update_fields,
            "$push": {
                "decisions": decision_entry,
                "notes": {
                    "username": current_user["username"],
                    "role": current_user["role"],
                    "timestamp": now,
                    "note": f"Decision submitted: {payload.decision.upper()}. Comment: {payload.comment} (Version {new_version})."
                },
                "audit_logs": audit_entry
            }
        }
    )
    
    # Update document status in documents collection
    await documents_col.update_one(
        {"_id": doc_oid},
        {"$set": {"status": doc_status}}
    )
    
    # Sync case status
    try:
        case_decision_map = {
            "approve": "APPROVED",
            "reject": "REJECTED",
            "escalate": "ESCALATED",
            "waitlist": "CLOSED"
        }
        await sync_doc_workflow_to_case(
            document_id=analysis_doc["document_id"],
            workflow_status=case_decision_map[payload.decision],
            manager=current_user["username"],
            comment=payload.comment,
            user_role=current_user["role"],
            username=current_user["username"]
        )
    except Exception:
        pass

    # Notify Underwriter and Fraud Analyst
    doc = await documents_col.find_one({"_id": doc_oid})
    if doc:
        underwriter = doc.get("uploaded_by") or "system"
        filename = doc.get("original_filename") or doc.get("filename", "document")
        assigned_analyst = analysis_doc.get("workflow", {}).get("assigned_analyst")
        
        # Notify Underwriter
        try:
            await create_notification(
                db=analyses_col.database,
                recipient_username=underwriter,
                document_id=analysis_id,
                document_name=filename,
                message=f"Document '{filename}' was {payload.decision.upper()}D by manager {current_user['username']}. Comment: {payload.comment}",
                type=payload.decision
            )
        except Exception as e:
            logger.warning(f"Failed to create manager notification for underwriter: {e}")
            
        # Notify Fraud Analyst
        if assigned_analyst:
            try:
                await create_notification(
                    db=analyses_col.database,
                    recipient_username=assigned_analyst,
                    document_id=analysis_id,
                    document_name=filename,
                    message=f"Document '{filename}' under your review has been {payload.decision.upper()}D by manager {current_user['username']}. Comment: {payload.comment}",
                    type=payload.decision
                )
            except Exception as e:
                logger.warning(f"Failed to create manager notification for analyst: {e}")
    
    # Write to compliance audit log
    try:
        audit_col = get_collection("audit_logs")
        await audit_col.insert_one({
            "timestamp": now,
            "user_id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "action": f"decision_{payload.decision}",
            "details": {
                "analysis_id": analysis_id,
                "document_id": str(doc_oid),
                "comment": payload.comment
            }
        })
    except Exception:
        pass
        
    return {"status": "success", "message": f"Case has been {payload.decision}ed successfully", "version": new_version}

