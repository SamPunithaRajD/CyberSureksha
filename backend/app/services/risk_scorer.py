"""
Risk Scorer — Composite fraud risk scoring engine.
Implements a deterministic weighted scoring system to strongly differentiate
clean vs tampered documents. Generates enterprise-grade recommendations.
"""

from typing import Any
import numpy as np
from loguru import logger

class RiskScorer:
    """Compute a deterministic composite fraud risk score and confidence."""

    def __init__(self) -> None:
        # Score tier boundaries (4-tier system)
        self.thresholds = {
            "verified": 25,
            "low_risk": 45,
            "review": 70,
        }

    # ------------------------------------------------------------------ #
    #  Core scoring
    # ------------------------------------------------------------------ #
    def process(
        self,
        ocr_result: dict,
        metadata_result: dict,
        tampering_result: dict,
        signature_result: dict,
        amount_result: dict,
        anomaly_result: dict,
    ) -> dict:
        logger.info("Computing deterministic composite risk score and confidence")

        score = 15.0 # Base starting score
        detected_issues = []

        # Collect all anomalies from all services
        all_anomalies = []
        all_anomalies.extend(metadata_result.get("anomalies", []))
        all_anomalies.extend(tampering_result.get("anomalies", []))
        all_anomalies.extend(signature_result.get("anomalies", []))
        all_anomalies.extend(amount_result.get("anomalies", []))
        
        # Anomaly detector outputs multiple lists
        all_anomalies.extend(anomaly_result.get("text_anomalies", []))
        all_anomalies.extend(anomaly_result.get("cross_field_anomalies", []))
        all_anomalies.extend(anomaly_result.get("pattern_anomalies", []))
        all_anomalies.extend(anomaly_result.get("cross_document_anomalies", []))
        all_anomalies.extend(anomaly_result.get("structured_anomalies", []))
        all_anomalies.extend(anomaly_result.get("banking_anomalies", []))

        # We also need to map the "old" anomaly structures to the new UI structure
        # The new UI structure expects: issue, severity, confidence, recommendation
        
        has_metadata_anomaly = False
        has_low_ocr = False
        has_transaction_manipulation = False
        has_payslip_math_inconsistency = False

        doc_type = ocr_result.get("document_type", "Unknown")
        if doc_type == "Unknown":
            full_text = ocr_result.get("extraction", {}).get("full_text", "").lower()
            if "bank" in full_text and ("statement" in full_text or "balance" in full_text or "account no" in full_text or "withdrawals" in full_text):
                doc_type = "Bank Statement"

        for anomaly in all_anomalies:
            a_type = anomaly.get("type", "").lower()
            a_issue = anomaly.get("issue", anomaly.get("description", "Unknown issue"))
            
            # Skip technical ELA, copy-move, noise, and edge anomalies for bank statements
            if doc_type == "Bank Statement":
                if any(t in a_type for t in ["compression", "ela_tampering", "copy_move", "noise", "edge", "pixel"]) or \
                   any(t in a_issue.lower() for t in ["compression", "pixel anomaly", "ela"]):
                    continue
                    
            penalty = 0

            # Map specific rules
            if "high_ocr_confidence" in a_type:
                score -= 5
                continue # don't add to detected issues
            elif "low_ocr_confidence" in a_type:
                penalty = 15
                has_low_ocr = True
            elif "low_ocr_field_confidence" in a_type:
                penalty = 10
            elif "metadata_mismatch" in a_type or "metadata" in a_type:
                penalty = 20
                has_metadata_anomaly = True
            elif "salary_manipulation" in a_type:
                penalty = 35
            elif "payslip_math_inconsistency" in a_type:
                penalty = 30
                if anomaly.get("severity", "").lower() in ["critical", "high"]:
                    has_payslip_math_inconsistency = True
            elif "bank_transaction_manipulation" in a_type:
                penalty = 40
                if anomaly.get("severity", "").lower() in ["critical", "high"]:
                    has_transaction_manipulation = True
            elif "bank_balance_inconsistency" in a_type:
                penalty = 25
            elif "duplicate_transactions" in a_type:
                penalty = 15
            elif "suspicious_stamp_duty" in a_type:
                penalty = 10
            elif "transaction_inconsistency" in a_type or "benfords" in a_type:
                penalty = 20
            elif "suspicious_formatting" in a_type or "format" in a_type:
                penalty = 15
            elif "font" in a_type:
                penalty = 15
            elif "signature_mismatch" in a_type or "signature" in a_type:
                penalty = 25
            elif "compression" in a_type or "ela_tampering" in a_type or "copy_move" in a_type or "noise" in a_type or "edge" in a_type:
                penalty = 2.0
                a_issue = "Compression or Pixel Anomaly"
            elif "duplicate_regions" in a_type:
                penalty = 20
            elif "future_date" in a_type:
                penalty = 25
            elif "impossible_timeline" in a_type:
                penalty = 35
            elif "transaction_outside_statement_period" in a_type:
                penalty = 25
            elif "multiple_pan" in a_type or "identity_mismatch" in a_type or "pan_mismatch" in a_type:
                penalty = 30
            elif "name_consistency_mismatch" in a_type:
                penalty = 25
            elif "unusual_symbol_detection" in a_type:
                penalty = 15
            elif "bank_name_spelling_mismatch" in a_type:
                penalty = 15
            elif "unregistered_bank_name" in a_type:
                penalty = 40
            elif "account_number_mismatch" in a_type:
                penalty = 40
            elif "ifsc_format_mismatch" in a_type:
                penalty = 25
            elif "ifsc_bank_mismatch" in a_type:
                penalty = 40
            elif "outdated_salary_slip" in a_type:
                penalty = 15
            elif "suspicious_salary_schedule" in a_type:
                penalty = 30
            elif "short_text" in a_type:
                penalty = 5
            else:
                penalty = 5 # default penalty

            score += penalty

            # Resolve page number
            page_val = anomaly.get("page") or anomaly.get("evidence", {}).get("page")
            if not page_val:
                det_val = anomaly.get("evidence", {}).get("detected_value") or anomaly.get("detected_value")
                exp_val = anomaly.get("evidence", {}).get("expected_value") or anomaly.get("expected_value")
                
                block = None
                if det_val:
                    block = self._find_block_by_text(det_val, ocr_result)
                if not block and exp_val:
                    block = self._find_block_by_text(exp_val, ocr_result)
                
                if block:
                    page_val = block.get("page", 1)
                else:
                    page_val = 1
            else:
                try:
                    page_val = int(page_val)
                except Exception:
                    page_val = 1

            # Resolve coordinates/bbox with robust fallback logic
            bbox_val = anomaly.get("bbox") or anomaly.get("evidence", {}).get("bbox")
            field_name = anomaly.get("field")
            
            if not bbox_val:
                # 1. Try to find by field name in structured data
                if field_name:
                    field_map = {
                        "Account Holder": "account_holder",
                        "Customer Name": "account_holder",
                        "Account Number": "account_number",
                        "Bank Name": "bank_name",
                        "Opening Balance": "opening_balance",
                        "Closing Balance": "closing_balance",
                        "IFSC Code": "ifsc_code",
                        "Statement Start Date": "statement_start_date",
                        "Statement End Date": "statement_end_date",
                        "Gross Salary": "gross_salary",
                        "Net Salary": "net_salary",
                        "Basic Salary": "basic_salary",
                        "Allowances": "allowances",
                        "Bonus": "bonus",
                        "Tax Deduction": "tax_deduction"
                    }
                    field_key = field_map.get(field_name)
                    if field_key:
                        struct_field = ocr_result.get("structured_data", {}).get(field_key)
                        if isinstance(struct_field, dict):
                            bbox_val = struct_field.get("bbox")
                
            if not bbox_val:
                # 2. Try to find by text lookup
                det_val = anomaly.get("evidence", {}).get("detected_value") or anomaly.get("detected_value")
                exp_val = anomaly.get("evidence", {}).get("expected_value") or anomaly.get("expected_value")
                
                block = None
                if det_val:
                    block = self._find_block_by_text(det_val, ocr_result)
                if not block and exp_val:
                    block = self._find_block_by_text(exp_val, ocr_result)
                
                if block:
                    bbox_val = block.get("bbox")

            if not bbox_val:
                # 3. For tampering anomalies, try using ELA or copy_move regions
                if "tampering" in a_type or "compression" in a_type or "ela" in a_type:
                    regions = tampering_result.get("ela", {}).get("suspicious_regions", []) or tampering_result.get("copy_move", {}).get("regions", [])
                    if regions:
                        first_region = regions[0]
                        if isinstance(first_region, dict):
                            bbox_val = first_region.get("bbox")

            if not bbox_val:
                # 4. For signature anomalies, try using signature verifier locations
                if "signature" in a_type:
                    locations = signature_result.get("signature_locations", [])
                    if locations:
                        bbox_val = locations[0].get("bbox")

            if not bbox_val:
                # 5. Default fallback to first block on the resolved page
                extraction = ocr_result.get("extraction", {})
                pages = extraction.get("pages", [])
                fallback_block = None
                for p in pages:
                    if p.get("page_num") == page_val:
                        p_blocks = p.get("blocks", [])
                        if p_blocks:
                            fallback_block = p_blocks[0]
                            break
                if not fallback_block and extraction.get("blocks"):
                    fallback_block = extraction.get("blocks")[0]
                
                if fallback_block:
                    bbox_val = fallback_block.get("bbox")
                else:
                    bbox_val = [5.0, 5.0, 90.0, 10.0]

            # Enforce non-empty fallback fields
            if not field_name:
                if "metadata" in a_type:
                    field_name = "Document Metadata"
                elif "tampering" in a_type or "compression" in a_type or "ela" in a_type:
                    field_name = "Image Layer"
                elif "signature" in a_type:
                    field_name = "Signature Block"
                elif "amount" in a_type or "financial" in a_type or "benfords" in a_type:
                    field_name = "Financial Fields"
                else:
                    field_name = "Document Integrity"

            detected_issues.append({
                "issue": anomaly.get("issue", a_issue),
                "severity": anomaly.get("severity", "Medium").capitalize(),
                "confidence": int(anomaly.get("confidence", 0.85) * 100) if isinstance(anomaly.get("confidence"), float) else anomaly.get("confidence", 85),
                "recommendation": anomaly.get("recommendation", "Review document manually."),
                "penalty": penalty,
                "field": field_name,
                "detected_value": anomaly.get("evidence", {}).get("detected_value") or anomaly.get("detected_value"),
                "expected_value": anomaly.get("evidence", {}).get("expected_value") or anomaly.get("expected_value"),
                "bbox": bbox_val,
                "page": page_val
            })

        # Apply negative bonuses if clean
        if not has_metadata_anomaly and len(detected_issues) == 0:
            score = min(score, 20.0)

        # Hard Safety Rules
        critical_high_count = sum(1 for a in detected_issues if a["severity"] in ["Critical", "High"])
        has_salary_manipulation = any(a["issue"].lower() == "salary manipulation" for a in detected_issues)
        has_high_signature = any("signature" in a["issue"].lower() and a["severity"] in ["Critical", "High"] for a in detected_issues)
        has_unregistered_bank = any("unregistered bank name" in a["issue"].lower() for a in detected_issues)
        has_acc_mismatch = any("account number consistency mismatch" in a["issue"].lower() or "account number masking mismatch" in a["issue"].lower() for a in detected_issues)
        has_ifsc_bank_mismatch = any("ifsc bank prefix mismatch" in a["issue"].lower() for a in detected_issues)
        has_name_mismatch = any(("name consistency mismatch" in a["issue"].lower() or "surname altered" in a["issue"].lower()) and a["severity"] in ["Critical", "High"] for a in detected_issues)
        has_impossible_timeline = any("impossible statement period" in a["issue"].lower() for a in detected_issues)

        if has_transaction_manipulation or has_unregistered_bank or has_acc_mismatch or has_ifsc_bank_mismatch or has_impossible_timeline:
            score = max(score, 85.0)
        elif has_payslip_math_inconsistency or has_name_mismatch:
            score = max(score, 75.0)
        elif has_salary_manipulation and has_metadata_anomaly:
            score = max(score, 80.0)
        elif has_high_signature:
            score = max(score, 75.0)
        
        if critical_high_count >= 1:
            score = max(score, 50.0) # Ensure at least review
        if critical_high_count >= 2:
            score = max(score, 75.0) # Ensure heavy manipulation doesn't slip

        # Ensure bounds
        composite = float(np.clip(score, 5.0, 95.0))
        
        # Limit clean documents
        if len(detected_issues) == 0:
            composite = float(np.clip(composite, 5.0, 10.0))

        # --- Tier ---
        tier = self._score_to_tier(composite)
        recommendation = self._tier_to_recommendation(tier)

        # --- Confidence score ---
        analysis_confidence = self._calculate_overall_confidence(ocr_result, tampering_result, signature_result)

        # --- Prepare "Detected Issues" output schema ---
        # Deduplicate issues by name to prevent stacking in the UI
        unique_issues = {}
        for issue in detected_issues:
            if issue["issue"] not in unique_issues:
                unique_issues[issue["issue"]] = issue
        
        final_detected_issues = list(unique_issues.values())

        # Sort by Severity
        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        final_detected_issues.sort(key=lambda x: (severity_order.get(x["severity"], 99), -x["penalty"]))

        # Assign IDs and normalize bboxes
        highlight_regions = []
        for idx, issue in enumerate(final_detected_issues):
            issue_id = f"issue_{idx + 1}"
            issue["issue_id"] = issue_id
            
            raw_bbox = issue.get("bbox")
            if raw_bbox:
                bbox_id = f"bbox_{idx + 1}"
                normalized = self._normalize_bbox(raw_bbox, issue["severity"], issue["issue"])
                if normalized:
                    normalized["page"] = int(issue["page"])
                    issue["bbox"] = normalized
                    issue["bbox_id"] = bbox_id
                    highlight_regions.append({
                        "bbox_id": bbox_id,
                        **normalized
                    })
                else:
                    issue["bbox"] = None
                    issue["bbox_id"] = None
            else:
                issue["bbox"] = None
                issue["bbox_id"] = None

        # Check for auto-reject escalation
        if critical_high_count > 3:
            tier = "high_risk"
            composite = max(composite, 90.0)

        # Initial workflow status & priority (always UNASSIGNED to go to Analyst first)
        workflow_status = "UNASSIGNED"
        priority = "CRITICAL" if tier == "high_risk" else ("HIGH" if tier == "review" else ("MEDIUM" if tier == "low_risk" else "LOW"))

        logger.info(f"Composite score: {composite:.1f} (Conf: {analysis_confidence:.1f}%) — {tier}")
        
        return {
            "composite": round(composite, 2),
            "tier": tier,
            "recommendation": recommendation,
            "analysis_confidence": analysis_confidence,
            "metrics": {
                "ocr_confidence": round(ocr_result.get("extraction", {}).get("avg_confidence", 0) * 100 if ocr_result.get("extraction", {}).get("avg_confidence", 0) <= 1.0 else ocr_result.get("extraction", {}).get("avg_confidence", 0), 1),
                "metadata_reliability": round(max(100.0 - metadata_result.get("risk_score", 0), 0), 1),
                "fraud_detection_confidence": analysis_confidence,
            },
            "detected_issues": final_detected_issues,
            "sub_scores": {
                "metadata": metadata_result.get("risk_score", 0),
                "tampering": 0.0 if doc_type == "Bank Statement" else tampering_result.get("composite_score", 0),
                "signature": signature_result.get("risk_score", 0),
                "amount": amount_result.get("risk_score", 0),
                "anomaly": anomaly_result.get("risk_score", 0)
            },
            "workflow": {
                "status": workflow_status,
                "assigned_analyst": None,
                "assigned_manager": None,
                "priority": priority,
                "escalation_reason": None,
                "escalated_by": None
            },
            "highlight_regions": highlight_regions
        }

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    def _score_to_tier(self, score: float) -> str:
        if score <= self.thresholds["verified"]:
            return "verified"
        elif score <= self.thresholds["low_risk"]:
            return "low_risk"
        elif score <= self.thresholds["review"]:
            return "review"
        return "high_risk"

    @staticmethod
    def _tier_to_recommendation(tier: str) -> str:
        mapping = {
            "verified": "Automatic approval recommended. No manual underwriting review required.",
            "low_risk": "Low risk identified. Standard processing can continue.",
            "review": "Manual underwriting review required. Please inspect flagged issues.",
            "high_risk": "Manual underwriting review required before approval. High fraud risk detected.",
        }
        return mapping.get(tier, "Manual underwriting review required.")

    def _calculate_overall_confidence(self, ocr_result: dict, tampering_result: dict, signature_result: dict) -> float:
        confidences = []
        
        ocr_conf = ocr_result.get("extraction", {}).get("avg_confidence", 0)
        if isinstance(ocr_conf, (int, float)) and ocr_conf > 0:
            val = ocr_conf * 100 if ocr_conf <= 1.0 else ocr_conf
            confidences.append(val)
            
        tamp_conf = tampering_result.get("confidence", 95.0)
        confidences.append(tamp_conf)
        
        sig_conf = signature_result.get("confidence", 90.0)
        confidences.append(sig_conf)
        
        if not confidences:
            return 94.0
            
        overall = float(np.mean(confidences))
        return round(np.clip(overall, 0.0, 100.0), 2)

    @staticmethod
    def _normalize_bbox(bbox: Any, severity: str, label: str) -> dict | None:
        if not bbox:
            return None
        if isinstance(bbox, dict):
            return {
                "x": float(bbox.get("x", 0)),
                "y": float(bbox.get("y", 0)),
                "width": float(bbox.get("width", 0)),
                "height": float(bbox.get("height", 0)),
                "severity": bbox.get("severity", severity).upper(),
                "label": bbox.get("label", label)
            }
        if isinstance(bbox, list) and len(bbox) == 4:
            return {
                "x": float(bbox[0]),
                "y": float(bbox[1]),
                "width": float(bbox[2]),
                "height": float(bbox[3]),
                "severity": severity.upper(),
                "label": label
            }
        return None

    @staticmethod
    def _find_block_by_text(text_val: Any, ocr_result: dict) -> dict | None:
        import re
        if not text_val or not ocr_result:
            return None
        text_clean = re.sub(r"[₹\s,.\-\:\*X]", "", str(text_val)).lower()
        if not text_clean:
            return None
            
        extraction = ocr_result.get("extraction", {})
        blocks = []
        if "blocks" in extraction:
            for b in extraction.get("blocks", []):
                b_copy = dict(b)
                if "page" not in b_copy:
                    b_copy["page"] = 1
                blocks.append(b_copy)
        if "pages" in extraction:
            for page in extraction["pages"]:
                p_num = page.get("page_num", 1)
                for b in page.get("blocks", []):
                    b_copy = dict(b)
                    b_copy["page"] = p_num
                    blocks.append(b_copy)
                
        for b in blocks:
            b_text_clean = re.sub(r"[₹\s,.\-\:\*X]", "", b.get("text", "")).lower()
            if text_clean in b_text_clean or b_text_clean in text_clean:
                return b
        return None

    def calculate_case_scores(
        self,
        doc_results: list[dict[str, Any]],
        cross_anomalies: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Computes the aggregate case-level risk score and Trust score across all documents.
        """
        logger.info("Calculating Case-level Financial Risk and Trust Scores")
        
        # 1. Base scores from documents
        doc_scores = [d.get("risk_score", {}).get("composite", 0.0) for d in doc_results]
        max_doc_score = max(doc_scores) if doc_scores else 0.0
        
        # 2. Add penalties for cross-document inconsistencies
        cross_penalty = 0.0
        detected_issues = []
        
        # Subscore categories for Trust
        identity_trust = 100.0
        financial_trust = 100.0
        document_trust = 100.0
        metadata_trust = 100.0
        
        for idx, doc in enumerate(doc_results):
            # Gather sub-scores for averaging
            d_sub = doc.get("risk_score", {}).get("sub_scores", {})
            metadata_trust -= d_sub.get("metadata", 0.0) * 0.5
            document_trust -= d_sub.get("tampering", 0.0) * 0.4
            document_trust -= d_sub.get("signature", 0.0) * 0.2
            financial_trust -= d_sub.get("amount", 0.0) * 0.3
            identity_trust -= d_sub.get("anomaly", 0.0) * 0.3

            # Propagate issues
            doc_issues = doc.get("risk_score", {}).get("detected_issues", [])
            for iss in doc_issues:
                detected_issues.append({
                    "issue": f"[{doc.get('original_filename', f'Doc {idx+1}')}] {iss.get('issue')}",
                    "severity": iss.get("severity", "MEDIUM"),
                    "confidence": iss.get("confidence", 0.9),
                    "recommendation": iss.get("recommendation", ""),
                    "bbox": iss.get("bbox")
                })

        for anomaly in cross_anomalies:
            field = anomaly.get("field", "")
            severity = anomaly.get("severity", "HIGH").upper()
            penalty = 0.0
            
            if field in ("name", "pan", "aadhaar"):
                penalty = 30.0 if severity == "CRITICAL" else 20.0
                identity_trust -= penalty
            elif field in ("salary_amount", "account_number"):
                penalty = 35.0 if severity == "CRITICAL" else 25.0
                financial_trust -= penalty
            elif field == "ifsc":
                penalty = 15.0
                financial_trust -= penalty
            else:
                penalty = 15.0
                document_trust -= penalty
                
            cross_penalty += penalty
            
            detected_issues.append({
                "issue": f"[Cross-Document] {anomaly.get('description')}",
                "severity": severity,
                "confidence": anomaly.get("confidence", 0.95),
                "recommendation": anomaly.get("recommendation", "")
            })

        # Calculate composite case risk score
        composite_score = max_doc_score + (cross_penalty * 0.6)
        composite_score = round(min(100.0, max(0.0, composite_score)), 2)
        
        # Calculate sub-score categorizations for response
        # Keep trust score bound between 0 and 100
        identity_trust = max(0.0, min(100.0, identity_trust))
        financial_trust = max(0.0, min(100.0, financial_trust))
        document_trust = max(0.0, min(100.0, document_trust))
        metadata_trust = max(0.0, min(100.0, metadata_trust))
        
        trust_score_val = round((identity_trust + financial_trust + document_trust + metadata_trust) / 4.0, 2)
        
        # Deduce Trust category
        if trust_score_val >= 85:
            trust_cat = "High Trust Profile"
        elif trust_score_val >= 60:
            trust_cat = "Medium Trust / Verify"
        else:
            trust_cat = "Low Trust / Suspicious"
            
        # Determine composite risk tier
        if composite_score >= 70:
            tier = "high_risk" # Map to standard high_risk tier
        elif composite_score >= 45:
            tier = "review"
        elif composite_score >= 25:
            tier = "low_risk"
        else:
            tier = "verified"

        # Map to visual risk tiers (Low, Medium, High, Critical)
        if composite_score >= 80:
            display_tier = "CRITICAL RISK"
        elif composite_score >= 50:
            display_tier = "HIGH RISK"
        elif composite_score >= 25:
            display_tier = "MEDIUM RISK"
        else:
            display_tier = "LOW RISK"

        return {
            "composite": composite_score,
            "tier": tier,
            "display_tier": display_tier,
            "recommendation": self._tier_to_recommendation(tier),
            "detected_issues": detected_issues,
            "sub_scores": {
                "metadata": round(100 - metadata_trust, 2),
                "tampering": round(100 - document_trust, 2),
                "signature": 0.0,
                "amount": round(100 - financial_trust, 2),
                "anomaly": round(100 - identity_trust, 2),
                "cross_document": round(cross_penalty, 2)
            },
            "trust_score": {
                "score": trust_score_val,
                "category": trust_cat,
                "sub_scores": {
                    "identity": round(identity_trust, 2),
                    "financial": round(financial_trust, 2),
                    "document": round(document_trust, 2),
                    "metadata": round(metadata_trust, 2)
                }
            }
        }
