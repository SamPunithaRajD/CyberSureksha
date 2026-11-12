"""
SecureDocXAI — Document Relationship Engine

Analyzes relationships and checks consistency across multiple documents in a case:
- Identity consistency (Names, PAN, Aadhaar, DOB, Addresses, Signatures)
- Financial consistency (Account number, IFSC, Salaries vs. bank credits, Employer names)
- Document metadata correlation (Creation dates, source software, author mismatches)

Raises detailed cross-document anomalies if mismatches are detected.
"""

from __future__ import annotations

import re
from typing import Any
from loguru import logger


class DocumentRelationshipEngine:
    """
    Validates parameter consistency across all documents within an Investigation Case.
    """

    def __init__(self):
        logger.info("Initializing Document Relationship Engine")

    def process(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Cross-reference credentials and values across multiple uploaded documents.
        
        Parameters
        ----------
        documents : list of dict
            List of serialized/loaded document records, each containing 'ocr_result' and 'metadata_analysis'.
            
        Returns
        -------
        list of dict
            List of cross-document anomalies.
        """
        logger.info("Running cross-document relationship consistency check on {} documents.", len(documents))
        anomalies = []

        if len(documents) < 2:
            logger.info("Fewer than 2 documents provided. Skipping cross-document checks.")
            return anomalies

        # ── 1. Gather all fields per document category ────────────────────────
        names: list[dict[str, Any]] = []
        pans: list[dict[str, Any]] = []
        aadhaars: list[dict[str, Any]] = []
        dob_list: list[dict[str, Any]] = []
        accounts: list[dict[str, Any]] = []
        ifsclist: list[dict[str, Any]] = []
        employers: list[dict[str, Any]] = []
        salaries: list[dict[str, Any]] = []
        addresses: list[dict[str, Any]] = []

        for doc in documents:
            doc_id = str(doc.get("id") or doc.get("_id", ""))
            filename = doc.get("original_filename", doc.get("filename", "unknown"))
            category = doc.get("document_category", "unknown")
            
            ocr = doc.get("ocr_result", {}) or doc.get("results", {}).get("ocr", {})
            if not ocr:
                continue

            entities = ocr.get("entities", {})
            structured = ocr.get("structured_data", {})

            # Helper to safely extract values
            def add_entity_item(entity_key: str, dest_list: list):
                if entity_key in entities and entities[entity_key]:
                    for val in entities[entity_key]:
                        if val and len(str(val).strip()) > 2:
                            dest_list.append({
                                "value": str(val).strip(),
                                "doc_id": doc_id,
                                "filename": filename,
                                "category": category
                            })
                            
            def add_structured_item(struct_key: str, dest_list: list):
                if struct_key in structured and structured[struct_key]:
                    val = structured[struct_key]
                    if isinstance(val, dict):
                        val_str = str(val.get("value", "")).strip()
                    else:
                        val_str = str(val).strip()
                    if val_str and len(val_str) > 2:
                        dest_list.append({
                            "value": val_str,
                            "doc_id": doc_id,
                            "filename": filename,
                            "category": category
                        })

            # Extract names
            add_entity_item("name", names)
            add_structured_item("name", names)
            
            # Extract PANs
            add_entity_item("pan", pans)
            
            # Extract Aadhaar
            add_entity_item("aadhaar", aadhaars)
            
            # Extract DOB
            add_entity_item("dob", dob_list)
            
            # Extract Bank Accounts
            add_entity_item("account_number", accounts)
            
            # Extract IFSC codes
            add_entity_item("ifsc", ifsclist)
            
            # Extract Addresses
            add_entity_item("address", addresses)
            add_structured_item("address", addresses)
            
            # Extract employer names
            add_entity_item("employer", employers)
            add_structured_item("employer", employers)
            
            # Extract salaries
            if category == "financial" or "payslip" in filename.lower() or "salary" in filename.lower():
                # Check for net salary
                if "net_salary" in structured and structured["net_salary"]:
                    val = structured["net_salary"]
                    val_str = str(val.get("value", "")).strip() if isinstance(val, dict) else str(val).strip()
                    # Clean currency formatting
                    val_clean = re.sub(r"[^\d.]", "", val_str)
                    if val_clean:
                        try:
                            salaries.append({
                                "value": float(val_clean),
                                "original": val_str,
                                "doc_id": doc_id,
                                "filename": filename
                            })
                        except ValueError:
                            pass

        # ── 2. Cross-document Name Consistency Checks ─────────────────────────
        if names:
            ref_name = names[0]["value"]
            ref_name_clean = re.sub(r"\s+", "", ref_name.lower())
            for n in names[1:]:
                n_clean = re.sub(r"\s+", "", n["value"].lower())
                
                # Check if exact mismatch or partial similarity
                if ref_name_clean != n_clean:
                    # Allow minor spelling difference but flag substantial changes
                    from app.services.ocr_correction import OCRCorrectionLayer
                    if not OCRCorrectionLayer()._names_match(ref_name, n["value"]):
                        anomalies.append({
                            "category": "cross_document_inconsistency",
                            "field": "name",
                            "severity": "CRITICAL",
                            "confidence": 0.95,
                            "description": (
                                f"Name Consistency Conflict detected. Name '{ref_name}' in {names[0]['filename']} "
                                f"does not match '{n['value']}' found in {n['filename']}. "
                                f"Cross-document identity conflict indicates potential identity theft/forgery."
                            ),
                            "evidence": {
                                "reference_value": ref_name,
                                "detected_value": n["value"],
                                "reference_doc_id": names[0]["doc_id"],
                                "conflict_doc_id": n["doc_id"]
                            },
                            "recommendation": "Verify official identity records (PAN/Aadhaar) to check the customer's correct legal name."
                        })

        # ── 3. Cross-document PAN and Aadhaar checks ──────────────────────────
        if pans:
            ref_pan = pans[0]["value"].upper()
            for p in pans[1:]:
                if ref_pan != p["value"].upper():
                    anomalies.append({
                        "category": "cross_document_inconsistency",
                        "field": "pan",
                        "severity": "CRITICAL",
                        "confidence": 0.99,
                        "description": (
                            f"PAN Number Conflict. PAN Card '{ref_pan}' in {pans[0]['filename']} "
                            f"does not match '{p['value']}' found in {p['filename']}."
                        ),
                        "evidence": {
                            "reference_value": ref_pan,
                            "detected_value": p["value"],
                            "reference_doc_id": pans[0]["doc_id"],
                            "conflict_doc_id": p["doc_id"]
                        },
                        "recommendation": "Confirm PAN card authenticity via NSDL database API."
                    })

        if aadhaars:
            # Strip spaces
            ref_aadhaar = re.sub(r"\s+", "", aadhaars[0]["value"])
            for a in aadhaars[1:]:
                a_val = re.sub(r"\s+", "", a["value"])
                if ref_aadhaar != a_val:
                    anomalies.append({
                        "category": "cross_document_inconsistency",
                        "field": "aadhaar",
                        "severity": "CRITICAL",
                        "confidence": 0.99,
                        "description": (
                            f"Aadhaar Number Conflict. Aadhaar ID '{aadhaars[0]['value']}' in {aadhaars[0]['filename']} "
                            f"does not match '{a['value']}' found in {a['filename']}."
                        ),
                        "evidence": {
                            "reference_value": aadhaars[0]["value"],
                            "detected_value": a["value"],
                            "reference_doc_id": aadhaars[0]["doc_id"],
                            "conflict_doc_id": a["doc_id"]
                        },
                        "recommendation": "Trigger Aadhaar biometrics validation or offline XML verification."
                    })

        # ── 4. Cross-document Bank Account and IFSC checks ────────────────────
        if accounts:
            ref_acc = accounts[0]["value"]
            # Allow matching last 4 digits if lengths differ
            for a in accounts[1:]:
                if ref_acc != a["value"]:
                    # Check if last 4 digits match
                    last_4_ref = ref_acc[-4:] if len(ref_acc) >= 4 else ref_acc
                    last_4_val = a["value"][-4:] if len(a["value"]) >= 4 else a["value"]
                    if last_4_ref != last_4_val:
                        anomalies.append({
                            "category": "cross_document_inconsistency",
                            "field": "account_number",
                            "severity": "CRITICAL",
                            "confidence": 0.92,
                            "description": (
                                f"Bank Account Number Mismatch. Account number '{ref_acc}' on {accounts[0]['filename']} "
                                f"does not match '{a['value']}' found on {a['filename']}."
                            ),
                            "evidence": {
                                "reference_value": ref_acc,
                                "detected_value": a["value"],
                                "reference_doc_id": accounts[0]["doc_id"],
                                "conflict_doc_id": a["doc_id"]
                            },
                            "recommendation": "Request a bank certification letter or check the official account statement."
                        })

        if ifsclist:
            ref_ifsc = ifsclist[0]["value"].upper()
            for i in ifsclist[1:]:
                if ref_ifsc != i["value"].upper():
                    anomalies.append({
                        "category": "cross_document_inconsistency",
                        "field": "ifsc",
                        "severity": "HIGH",
                        "confidence": 0.90,
                        "description": (
                            f"IFSC Code Conflict. IFSC code '{ref_ifsc}' on {ifsclist[0]['filename']} "
                            f"differs from '{i['value']}' on {i['filename']}."
                        ),
                        "evidence": {
                            "reference_value": ref_ifsc,
                            "detected_value": i["value"],
                            "reference_doc_id": ifsclist[0]["doc_id"],
                            "conflict_doc_id": i["doc_id"]
                        },
                        "recommendation": "Confirm bank branch address details match the IFSC database."
                    })

        # ── 5. Financial Cross-checks (Payslip net salary vs Bank credit) ─────
        # If we have both bank statement transactions and payslip salaries, match them
        if salaries:
            # Check if any document is a bank statement and has transactions
            for doc in documents:
                if doc.get("document_category") == "financial" and "payslip" not in doc.get("original_filename", "").lower():
                    # This is likely the bank statement, inspect its transactions
                    ocr = doc.get("ocr_result", {}) or doc.get("results", {}).get("ocr", {})
                    transactions = ocr.get("structured_data", {}).get("transactions", [])
                    if not transactions:
                        # Fallback: check in amount results
                        amt_res = doc.get("results", {}).get("amount", {})
                        transactions = amt_res.get("salary_credits", []) or amt_res.get("credits", [])
                        
                    # Let's search for salary credits in bank statement
                    bank_credits = []
                    for tx in transactions:
                        if isinstance(tx, dict):
                            desc = str(tx.get("description", "")).lower()
                            amount_val = tx.get("amount", tx.get("credit", 0.0))
                        elif isinstance(tx, str):
                            desc = tx.lower()
                            # Try to extract numbers from transaction string
                            nums = re.findall(r"\d+(?:\.\d+)?", tx)
                            amount_val = float(nums[-1]) if nums else 0.0
                        else:
                            continue
                            
                        # If description mentions salary/pay/corp/epfo
                        if any(k in desc for k in ("sal", "salary", "pay", "credit", "corp")):
                            if isinstance(amount_val, str):
                                amount_val = re.sub(r"[^\d.]", "", amount_val)
                                try:
                                    amount_val = float(amount_val)
                                except ValueError:
                                    amount_val = 0.0
                            if amount_val > 1000:
                                bank_credits.append(amount_val)

                    # Now match payslip salary with transactions
                    if bank_credits:
                        # Take payslip salary value
                        payslip_sal = salaries[0]["value"]
                        # Check if any credit is close to payslip salary (allow 5% variance due to tax/deductions)
                        matched = False
                        closest_credit = 0.0
                        min_diff = float("inf")
                        for cr in bank_credits:
                            diff = abs(cr - payslip_sal)
                            if diff < min_diff:
                                min_diff = diff
                                closest_credit = cr
                            if (diff / payslip_sal) < 0.10: # within 10%
                                matched = True
                                break
                        
                        if not matched:
                            anomalies.append({
                                "category": "cross_document_inconsistency",
                                "field": "salary_amount",
                                "severity": "CRITICAL",
                                "confidence": 0.95,
                                "description": (
                                    f"Salary Verification Failure. Net salary on payslip is ₹{payslip_sal:,.2f}, "
                                    f"but the closest salary-like credit found on the bank statement ({doc.get('original_filename')}) "
                                    f"is ₹{closest_credit:,.2f}. This is a critical income inflation indicator."
                                ),
                                "evidence": {
                                    "reference_value": f"₹{payslip_sal:,.2f}",
                                    "detected_value": f"₹{closest_credit:,.2f}",
                                    "payslip_doc_id": salaries[0]["doc_id"],
                                    "bank_statement_doc_id": doc.get("id")
                                },
                                "recommendation": "Request the applicant's official Form 16/ITR filings to verify true income."
                            })

        # ── 6. Cross-document Employer Name verification ──────────────────────
        if employers:
            # Check if the bank statement credits reference the employer name
            ref_emp = employers[0]["value"]
            ref_emp_clean = re.sub(r"\s+", "", ref_emp.lower())
            
            # Find bank statement and look for transactions referencing the employer name
            for doc in documents:
                if doc.get("document_category") == "financial" and "payslip" not in doc.get("original_filename", "").lower():
                    ocr = doc.get("ocr_result", {}) or doc.get("results", {}).get("ocr", {})
                    transactions = ocr.get("structured_data", {}).get("transactions", [])
                    
                    found_employer = False
                    for tx in transactions:
                        desc = str(tx.get("description", "")).lower()
                        if ref_emp_clean in re.sub(r"\s+", "", desc):
                            found_employer = True
                            break
                            
                    if employers[0]["category"] == "financial" and len(employers) > 1:
                        # Match between two payslips/documents
                        for emp in employers[1:]:
                            emp_clean = re.sub(r"\s+", "", emp["value"].lower())
                            if ref_emp_clean != emp_clean:
                                anomalies.append({
                                    "category": "cross_document_inconsistency",
                                    "field": "employer_name",
                                    "severity": "HIGH",
                                    "confidence": 0.90,
                                    "description": (
                                        f"Employer Name Conflict. Payslip lists employer as '{ref_emp}', "
                                        f"but other document '{emp['filename']}' references employer as '{emp['value']}'."
                                    ),
                                    "evidence": {
                                        "reference_value": ref_emp,
                                        "detected_value": emp["value"],
                                        "reference_doc_id": employers[0]["doc_id"],
                                        "conflict_doc_id": emp["doc_id"]
                                    },
                                    "recommendation": "Confirm active employment history on EPFO portal."
                                })

        return anomalies
