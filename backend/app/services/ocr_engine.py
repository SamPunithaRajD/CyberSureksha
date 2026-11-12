"""
DocuShield AI — OCR Engine Service
===================================
Production-grade OCR pipeline combining EasyOCR (image-based OCR) with
PyMuPDF native text extraction. Includes image preprocessing, spatial native PDF
block extraction, and type-specific structured data parsing with character confidences.
"""

import re
import threading
from pathlib import Path
from typing import Optional, Any

import cv2
import easyocr
import fitz  # PyMuPDF
import numpy as np
from loguru import logger


class StructuredOCRParser:
    """Extracts structured fields and computes their confidences/coordinates based on document classification."""

    def classify_document(self, text: str) -> str:
        text_lower = text.lower()
        if "bank" in text_lower and ("statement" in text_lower or "balance" in text_lower or "account no" in text_lower or "withdrawals" in text_lower):
            return "Bank Statement"
        elif "payslip" in text_lower or "salary slip" in text_lower or "net pay" in text_lower or "earnings" in text_lower:
            return "Payslip"
        elif "property" in text_lower or "deed" in text_lower or ("registration" in text_lower and "registration no" not in text_lower and "registration number" not in text_lower) or "stamp duty" in text_lower:
            return "Property Document"
        elif "id proof" in text_lower or "pan card" in text_lower or "aadhaar" in text_lower or "passport" in text_lower or "driving license" in text_lower or "income tax department" in text_lower:
            return "ID Proof"
        return "Unknown"

    def _find_block_details(self, matched_text: str, blocks: list[dict], default_conf: float = 90.0, page: int | None = None) -> tuple[float, list[float] | None]:
        if not matched_text or not blocks:
            return default_conf, None
        matched_clean = re.sub(r"[₹\s,.\-\:]", "", matched_text).lower()
        for b in blocks:
            if page is not None and b.get("page", 1) != page:
                continue
            b_text_clean = re.sub(r"[₹\s,.\-\:]", "", b.get("text", "")).lower()
            if matched_clean and b_text_clean and (matched_clean in b_text_clean or b_text_clean in matched_clean):
                return float(b.get("confidence", 0.9)) * 100.0, b.get("bbox")
        return default_conf, None

    def _extract_field_details(self, line: str, pattern: str, blocks: list[dict], default_val: Any = None, is_number: bool = True, page: int | None = None) -> dict:
        m = re.search(pattern, line, re.IGNORECASE)
        if m:
            matched_str = m.group(1) if len(m.groups()) >= 1 else m.group(0)
            full_match = m.group(0)
            val = matched_str.strip()
            if is_number:
                val = val.replace(",", "")
                try:
                    val = float(val)
                except ValueError:
                    val = default_val
            
            conf, bbox = self._find_block_details(full_match, blocks, page=page)
            return {
                "value": val,
                "confidence": conf,
                "bbox": bbox
            }
        return {
            "value": default_val,
            "confidence": 0.0,
            "bbox": None
        }

    def parse(self, text: str, blocks: list[dict], doc_type: str) -> tuple[dict, dict]:
        if doc_type == "Payslip":
            data = self.parse_payslip(text, blocks)
        elif doc_type == "Bank Statement":
            data = self.parse_bank_statement(text, blocks)
        elif doc_type == "Property Document":
            data = self.parse_property_document(text, blocks)
        elif doc_type == "ID Proof":
            data = self.parse_id_proof(text, blocks)
        else:
            data = {}

        # Post-process to ensure every field has a "page" key
        for key, val in data.items():
            if key == "transactions":
                tx_list = val.get("value", []) if isinstance(val, dict) else val
                if isinstance(tx_list, list):
                    for tx in tx_list:
                        if not isinstance(tx, dict):
                            continue
                        tx_page = 1
                        if tx.get("bbox"):
                            for b in blocks:
                                if b.get("bbox") == tx.get("bbox"):
                                    tx_page = b.get("page", 1)
                                    break
                        else:
                            for b in blocks:
                                if tx.get("date") in b.get("text", "") or tx.get("description") in b.get("text", ""):
                                    tx_page = b.get("page", 1)
                                    break
                        tx["page"] = tx_page
                if isinstance(val, dict):
                    val["page"] = 1
            elif isinstance(val, dict):
                field_page = 1
                if val.get("bbox"):
                    for b in blocks:
                        if b.get("bbox") == val.get("bbox"):
                            field_page = b.get("page", 1)
                            break
                elif val.get("value") and val.get("value") != "Unknown":
                    val_str = str(val.get("value"))
                    for b in blocks:
                        if val_str in b.get("text", ""):
                            field_page = b.get("page", 1)
                            break
                val["page"] = field_page

        # Build flat confidences dictionary for backward compatibility
        confidences = {k: v.get("confidence", 0.0) if isinstance(v, dict) else 90.0 for k, v in data.items()}
        return data, confidences

    def parse_payslip(self, text: str, blocks: list[dict]) -> dict:
        # Initial structures
        fields = ["employee_name", "basic_salary", "allowances", "bonus", "tax_deduction", "net_salary", "gross_salary", "account_number"]
        data = {f: {"value": 0.0 if f != "employee_name" and f != "account_number" else "Unknown", "confidence": 0.0, "bbox": None} for f in fields}

        # Normalize currency text
        normalized_text = text
        normalized_text = re.sub(r"\b[Ii|l]\s*(?=\d)", "₹", normalized_text)
        normalized_text = re.sub(r"(?<=[:\s\n])[Ii|l]\s*(?=\d)", "₹", normalized_text)

        lines = [l.strip() for l in normalized_text.split("\n") if l.strip()]

        # Extract Employee Name
        for idx, line in enumerate(lines):
            line_lower = line.lower()
            if "employee name" in line_lower or "name" in line_lower:
                m = re.search(r"(?:employee\s+)?name\s*[:\-]?\s*([a-zA-Z\s]+)", line, re.IGNORECASE)
                if m and m.group(1).strip() and len(m.group(1).strip()) > 3:
                    name = m.group(1).strip()
                    conf, bbox = self._find_block_details(name, blocks, 100.0)
                    data["employee_name"] = {"value": name, "confidence": conf, "bbox": bbox}
                    break
                elif idx + 1 < len(lines):
                    next_line = lines[idx+1]
                    if re.match(r"^[a-zA-Z\s]+$", next_line) and len(next_line) > 3:
                        conf, bbox = self._find_block_details(next_line, blocks, 100.0)
                        data["employee_name"] = {"value": next_line, "confidence": conf, "bbox": bbox}
                        break

        # Spatial lookup for name if not found
        if data["employee_name"]["value"] == "Unknown":
            for b in blocks:
                b_text = b.get("text", "").lower()
                if "employee name" in b_text or "name" in b_text:
                    bx1, by1, bx2, by2 = b["bbox"]
                    closest_right = None
                    min_dist = 999999
                    for ob in blocks:
                        ox1, oy1, ox2, oy2 = ob["bbox"]
                        if ox1 >= bx2 and abs(oy1 - by1) < 15:
                            dist = ox1 - bx2
                            if dist < min_dist:
                                min_dist = dist
                                closest_right = ob
                    if closest_right and re.match(r"^[a-zA-Z\s]+$", closest_right.get("text", "")):
                        name = closest_right.get("text", "").strip()
                        data["employee_name"] = {
                            "value": name,
                            "confidence": float(closest_right.get("confidence", 0.9)) * 100.0,
                            "bbox": closest_right.get("bbox")
                        }
                        break

        # Extract values
        for idx, line in enumerate(lines):
            line_lower = line.lower()
            res = self._extract_field_details(line, r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", blocks)
            if res["value"] is None and idx + 1 < len(lines):
                res = self._extract_field_details(lines[idx+1], r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", blocks)
            
            val = res["value"]
            if val is not None:
                if "basic" in line_lower or "base" in line_lower:
                    data["basic_salary"] = res
                elif "allowance" in line_lower or "hra" in line_lower:
                    data["allowances"] = {"value": (data["allowances"]["value"] or 0.0) + val, "confidence": max(data["allowances"]["confidence"], res["confidence"]), "bbox": res["bbox"]}
                elif "bonus" in line_lower or "performance" in line_lower:
                    data["bonus"] = res
                elif "deduction" in line_lower or "tax" in line_lower or "pf" in line_lower:
                    data["tax_deduction"] = {"value": (data["tax_deduction"]["value"] or 0.0) + val, "confidence": max(data["tax_deduction"]["confidence"], res["confidence"]), "bbox": res["bbox"]}
                elif "net" in line_lower:
                    data["net_salary"] = res
                elif "gross" in line_lower or "earnings" in line_lower:
                    data["gross_salary"] = res

            # Parse Account Number on Payslip
            if "account number" in line_lower or "account no" in line_lower or "ac no" in line_lower:
                res_ac = self._extract_field_details(line, r"(?:account\s+no|account\s+number|ac\s+no)\.?\s*[:\-]?\s*([0-9A-Za-z ]{8,20})", blocks, is_number=False)
                if res_ac["value"]:
                    data["account_number"] = {
                        "value": res_ac["value"].replace(" ", ""),
                        "confidence": res_ac["confidence"],
                        "bbox": res_ac["bbox"]
                    }

        # Spatial lookup for values
        for key, field in [
            ("basic", "basic_salary"),
            ("allowance", "allowances"),
            ("bonus", "bonus"),
            ("deduction", "tax_deduction"),
            ("net", "net_salary"),
            ("gross", "gross_salary"),
        ]:
            if data[field]["value"] == 0.0:
                for b in blocks:
                    b_text = b.get("text", "").lower()
                    if key in b_text:
                        bx1, by1, bx2, by2 = b["bbox"]
                        closest_right = None
                        min_dist = 999999
                        for ob in blocks:
                            ox1, oy1, ox2, oy2 = ob["bbox"]
                            if ox1 >= bx2 and abs(oy1 - by1) < 15:
                                dist = ox1 - bx2
                                if dist < min_dist:
                                    min_dist = dist
                                    closest_right = ob
                        if closest_right:
                            res = self._extract_field_details(closest_right.get("text", ""), r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", blocks)
                            if res["value"] is not None:
                                if field in ("allowances", "tax_deduction"):
                                    data[field] = {
                                        "value": data[field]["value"] + res["value"],
                                        "confidence": max(data[field]["confidence"], res["confidence"]),
                                        "bbox": res["bbox"]
                                    }
                                else:
                                    data[field] = res

        # Math fallback
        if data["net_salary"]["value"] == 0.0 and data["gross_salary"]["value"] > 0.0:
            data["net_salary"] = {
                "value": data["gross_salary"]["value"] - data["tax_deduction"]["value"],
                "confidence": min(data["gross_salary"]["confidence"], data["tax_deduction"]["confidence"]),
                "bbox": data["gross_salary"]["bbox"] or data["tax_deduction"]["bbox"]
            }
        elif data["gross_salary"]["value"] == 0.0 and data["net_salary"]["value"] > 0.0:
            data["gross_salary"] = {
                "value": data["net_salary"]["value"] + data["tax_deduction"]["value"],
                "confidence": min(data["net_salary"]["confidence"], data["tax_deduction"]["confidence"]),
                "bbox": data["net_salary"]["bbox"] or data["tax_deduction"]["bbox"]
            }

        if data["gross_salary"]["value"] == 0.0:
            data["gross_salary"] = {
                "value": data["basic_salary"]["value"] + data["allowances"]["value"] + data["bonus"]["value"],
                "confidence": min(c for c in [data["basic_salary"]["confidence"], data["allowances"]["confidence"], data["bonus"]["confidence"]] if c > 0) or 90.0,
                "bbox": data["basic_salary"]["bbox"] or data["allowances"]["bbox"]
            }
            if data["net_salary"]["value"] == 0.0:
                data["net_salary"] = {
                    "value": data["gross_salary"]["value"] - data["tax_deduction"]["value"],
                    "confidence": min(data["gross_salary"]["confidence"], data["tax_deduction"]["confidence"]),
                    "bbox": data["gross_salary"]["bbox"] or data["tax_deduction"]["bbox"]
                }

        return data

    def parse_bank_statement(self, text: str, blocks: list[dict]) -> dict:
        fields = ["account_holder", "account_number", "bank_name", "opening_balance", "closing_balance", "ifsc_code", "statement_start_date", "statement_end_date", "transactions"]
        data = {f: {"value": 0.0 if "balance" in f else "Unknown" if f != "transactions" else [], "confidence": 0.0, "bbox": None} for f in fields}

        normalized_text = text
        normalized_text = re.sub(r"\b[Ii|l]\s*(?=\d)", "₹", normalized_text)
        normalized_text = re.sub(r"(?<=[:\s\n])[Ii|l]\s*(?=\d)", "₹", normalized_text)

        # Detect Bank Name
        if "canara" in normalized_text.lower():
            data["bank_name"] = {"value": "Canara Bank", "confidence": 100.0, "bbox": None}
        elif "sbi" in normalized_text.lower() or "state bank" in normalized_text.lower():
            data["bank_name"] = {"value": "State Bank of India", "confidence": 100.0, "bbox": None}
        elif "hdfc" in normalized_text.lower():
            data["bank_name"] = {"value": "HDFC Bank", "confidence": 100.0, "bbox": None}
        elif "icici" in normalized_text.lower():
            data["bank_name"] = {"value": "ICICI Bank", "confidence": 100.0, "bbox": None}

        # Reconstruct lines
        reconstructed_lines = []
        reconstructed_line_pages = []
        if blocks:
            grouped_lines = []
            sorted_blocks = sorted(blocks, key=lambda b: (b.get("page", 1), b.get("bbox", [0, 0, 0, 0])[1]))
            
            for b in sorted_blocks:
                bbox = b.get("bbox")
                b_text = b.get("text", "").strip()
                page = b.get("page", 1)
                if not b_text or not bbox or len(bbox) != 4:
                    continue
                    
                y_top = bbox[1]
                y_height = bbox[3]
                y_center = y_top + y_height / 2
                
                merged = False
                for line in grouped_lines:
                    if line["page"] != page:
                        continue
                    line_y_center = line["y_center"]
                    line_height = line["height"]
                    
                    if abs(y_center - line_y_center) < 1.5 or abs(y_top - line["y_top"]) < (min(y_height, line_height) * 0.6):
                        line["blocks"].append(b)
                        line["y_center"] = (line["y_center"] * (len(line["blocks"]) - 1) + y_center) / len(line["blocks"])
                        line["y_top"] = min(line["y_top"], y_top)
                        line["height"] = max(line["height"], y_height)
                        merged = True
                        break
                        
                if not merged:
                    grouped_lines.append({
                        "page": page,
                        "y_center": y_center,
                        "y_top": y_top,
                        "height": y_height,
                        "blocks": [b]
                    })
                    
            for line in grouped_lines:
                sorted_line_blocks = sorted(line["blocks"], key=lambda b: b.get("bbox", [0, 0, 0, 0])[0])
                line_text = "   ".join(b.get("text", "").replace("\n", " ").strip() for b in sorted_line_blocks)
                if line_text.strip():
                    reconstructed_lines.append(line_text)
                    reconstructed_line_pages.append(line["page"])
        else:
            reconstructed_lines = [l.strip() for l in normalized_text.split("\n") if l.strip()]
            reconstructed_line_pages = [1] * len(reconstructed_lines)

        for idx, line in enumerate(reconstructed_lines):
            line_lower = line.lower()
            page = reconstructed_line_pages[idx]
            if "account holder" in line_lower or "holder name" in line_lower:
                m = re.search(r"account\s+holder\s*[:\-]?\s*([a-zA-Z\s]+)", line, re.IGNORECASE)
                if m and m.group(1).strip() and len(m.group(1).strip()) > 3:
                    name = m.group(1).strip()
                    conf, bbox = self._find_block_details(name, blocks, 100.0, page=page)
                    data["account_holder"] = {"value": name, "confidence": conf, "bbox": bbox}
                elif idx + 1 < len(reconstructed_lines):
                    next_line = reconstructed_lines[idx+1]
                    next_page = reconstructed_line_pages[idx+1]
                    if re.match(r"^[a-zA-Z\s]+$", next_line) and len(next_line) > 3:
                        conf, bbox = self._find_block_details(next_line, blocks, 100.0, page=next_page)
                        data["account_holder"] = {"value": next_line, "confidence": conf, "bbox": bbox}
            
            if "account number" in line_lower or "account no" in line_lower or "ac no" in line_lower:
                m = re.search(r"(?:account\s+no|account\s+number|ac\s+no|ac\s+number)\.?\s*[:\-]?\s*([0-9X\* ]{8,22})", line, re.IGNORECASE)
                if m:
                    ac = m.group(1).replace(" ", "").strip()
                    conf, bbox = self._find_block_details(m.group(1), blocks, 100.0, page=page)
                    data["account_number"] = {"value": ac, "confidence": conf, "bbox": bbox}
                elif idx + 1 < len(reconstructed_lines):
                    next_line = reconstructed_lines[idx+1]
                    next_page = reconstructed_line_pages[idx+1]
                    if re.match(r"^[0-9X\* ]{8,22}$", next_line.replace(" ", "")):
                        ac = next_line.replace(" ", "").strip()
                        conf, bbox = self._find_block_details(next_line, blocks, 100.0, page=next_page)
                        data["account_number"] = {"value": ac, "confidence": conf, "bbox": bbox}

        # Parse IFSC code
        m_ifsc = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", normalized_text, re.IGNORECASE)
        if m_ifsc:
            ifsc_val = m_ifsc.group(1).upper()
            conf, bbox = self._find_block_details(m_ifsc.group(0), blocks, 90.0)
            data["ifsc_code"] = {"value": ifsc_val, "confidence": conf, "bbox": bbox}

        # Parse statement period
        m_period = re.search(r"period\s*(?:of|from)?\s*([0-9a-zA-Z\-/ ]+)\s+to\s+([0-9a-zA-Z\-/ ]+)", normalized_text, re.IGNORECASE)
        if m_period:
            start_str = m_period.group(1).strip()
            end_str = m_period.group(2).strip()
            conf_s, bbox_s = self._find_block_details(start_str, blocks, 90.0)
            conf_e, bbox_e = self._find_block_details(end_str, blocks, 90.0)
            data["statement_start_date"] = {"value": start_str, "confidence": conf_s, "bbox": bbox_s}
            data["statement_end_date"] = {"value": end_str, "confidence": conf_e, "bbox": bbox_e}

        # Parse transactions
        date_pattern = r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{1,2}[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-\s]\d{4}\b"
        tx_list = []
        tx_confs = []

        for idx, line in enumerate(reconstructed_lines):
            line_lower = line.lower()
            page = reconstructed_line_pages[idx]
            if any(k in line_lower for k in ["statement period", "period", "date description", "transaction details", "note:"]):
                continue

            m_date = re.search(date_pattern, line, re.IGNORECASE)
            if m_date:
                date_str = m_date.group(0)
                line_no_date = line.replace(date_str, "").strip()
                
                # Extract amounts and confidences
                amounts_in_line = []
                for m_amt in re.finditer(r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", line_no_date):
                    cleaned = m_amt.group(1).replace(",", "")
                    try:
                        val = float(cleaned)
                        if val >= 1.0:
                            conf, bbox = self._find_block_details(m_amt.group(0), blocks, 90.0, page=page)
                            amounts_in_line.append((val, conf, bbox))
                    except ValueError:
                        pass
                
                desc = line_no_date
                for m_amt in re.finditer(r"(?:₹|Rs\.?|INR)?\s*[\d,]+(?:\.\d{1,2})?", line_no_date):
                    desc = desc.replace(m_amt.group(0), "")
                desc = re.sub(r"\s+", " ", desc).strip()
                desc = re.sub(r"^[:\-\s]+", "", desc).strip()
                desc = re.sub(r"^[–\-]+\s*", "", desc).strip()

                if len(amounts_in_line) >= 1:
                    credit = None
                    debit = None
                    balance = amounts_in_line[-1][0]
                    tx_conf = amounts_in_line[-1][1]
                    tx_bbox = amounts_in_line[-1][2]
                    
                    if len(amounts_in_line) >= 2:
                        tx_amt = amounts_in_line[0][0]
                        tx_conf = min(amounts_in_line[0][1], amounts_in_line[-1][1])
                        tx_bbox = amounts_in_line[0][2] or amounts_in_line[-1][2]
                        desc_lower = desc.lower()
                        if "credit" in desc_lower or "salary" in desc_lower or "deposit" in desc_lower or "refund" in desc_lower:
                            credit = tx_amt
                        else:
                            debit = tx_amt

                    if not any(k in desc.lower() for k in ["opening balance", "closing balance", "balance b/f", "balance c/f"]):
                        tx_list.append({
                            "date": date_str,
                            "description": desc,
                            "credit": credit,
                            "debit": debit,
                            "balance": balance,
                            "confidence": tx_conf,
                            "bbox": tx_bbox
                        })
                        tx_confs.append(tx_conf)

        data["transactions"] = {"value": tx_list, "confidence": round(sum(tx_confs) / len(tx_confs), 2) if tx_confs else 90.0, "bbox": None}

        # Parse opening and closing balance
        for idx, line in enumerate(reconstructed_lines):
            line_lower = line.lower()
            page = reconstructed_line_pages[idx]
            if "opening balance" in line_lower or "balance b/f" in line_lower:
                line_no_date = re.sub(date_pattern, "", line, flags=re.IGNORECASE).strip()
                res = self._extract_field_details(line_no_date, r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", blocks, page=page)
                if res["value"] is not None:
                    data["opening_balance"] = res
            if "closing balance" in line_lower or "balance c/f" in line_lower or "available balance" in line_lower:
                line_no_date = re.sub(date_pattern, "", line, flags=re.IGNORECASE).strip()
                res = self._extract_field_details(line_no_date, r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", blocks, page=page)
                if res["value"] is not None:
                    data["closing_balance"] = res

        # Fallbacks
        if data["opening_balance"]["value"] == 0.0 and tx_list:
            first_tx = tx_list[0]
            first_bal = first_tx["balance"]
            first_amt = (first_tx["credit"] or 0) - (first_tx["debit"] or 0)
            data["opening_balance"] = {"value": first_bal - first_amt, "confidence": first_tx["confidence"], "bbox": first_tx["bbox"]}

        if data["closing_balance"]["value"] == 0.0 and tx_list:
            data["closing_balance"] = {"value": tx_list[-1]["balance"], "confidence": tx_list[-1]["confidence"], "bbox": tx_list[-1]["bbox"]}

        return data

    def parse_property_document(self, text: str, blocks: list[dict]) -> dict:
        fields = ["owner_name", "registration_value", "stamp_duty", "land_area", "property_type"]
        data = {f: {"value": 0.0 if "value" in f or "duty" in f else "Unknown", "confidence": 0.0, "bbox": None} for f in fields}

        lines = [l.strip() for l in text.split("\n") if l.strip()]

        for idx, line in enumerate(lines):
            line_lower = line.lower()
            if "owner" in line_lower or "purchaser" in line_lower or "buyer" in line_lower or "name" in line_lower:
                m = re.search(r"(?:owner|purchaser|buyer|name)\s*[:\-]?\s*([a-zA-Z\s]+)", line, re.IGNORECASE)
                if m and len(m.group(1).strip()) > 3:
                    name = m.group(1).strip()
                    conf, bbox = self._find_block_details(name, blocks, 100.0)
                    data["owner_name"] = {"value": name, "confidence": conf, "bbox": bbox}
                    break

        for line in lines:
            line_lower = line.lower()
            res = self._extract_field_details(line, r"(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", blocks)
            if res["value"] is not None:
                if "stamp duty" in line_lower:
                    data["stamp_duty"] = res
                elif "registration" in line_lower:
                    data["registration_value"] = res

        # Extract land area
        for line in lines:
            line_lower = line.lower()
            if "area" in line_lower or "sq ft" in line_lower or "sq m" in line_lower or "sq yard" in line_lower:
                m = re.search(r"(\d+(?:\.\d+)?\s*(?:sq\s*ft|sq\s*m|square\s*feet|square\s*meters|guntas|acres))", line, re.IGNORECASE)
                if m:
                    area = m.group(1).strip()
                    conf, bbox = self._find_block_details(area, blocks, 90.0)
                    data["land_area"] = {"value": area, "confidence": conf, "bbox": bbox}
                    break

        # Property type
        if "residential" in text.lower():
            data["property_type"] = {"value": "Residential", "confidence": 100.0, "bbox": None}
        elif "commercial" in text.lower():
            data["property_type"] = {"value": "Commercial", "confidence": 100.0, "bbox": None}
        elif "agricultural" in text.lower() or "land" in text.lower():
            data["property_type"] = {"value": "Agricultural", "confidence": 100.0, "bbox": None}

        return data

    def parse_id_proof(self, text: str, blocks: list[dict]) -> dict:
        fields = ["id_type", "id_number", "name", "dob", "address"]
        data = {f: {"value": "Unknown", "confidence": 0.0, "bbox": None} for f in fields}

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        text_lower = text.lower()

        if "pan" in text_lower or "permanent account number" in text_lower:
            data["id_type"] = {"value": "PAN Card", "confidence": 100.0, "bbox": None}
            m = re.search(r"\b([A-Z]{5}\d{4}[A-Z])\b", text)
            if m:
                val = m.group(1)
                conf, bbox = self._find_block_details(val, blocks, 90.0)
                data["id_number"] = {"value": val, "confidence": conf, "bbox": bbox}
        elif "aadhaar" in text_lower or "uidai" in text_lower:
            data["id_type"] = {"value": "Aadhaar Card", "confidence": 100.0, "bbox": None}
            m = re.search(r"\b(\d{4}\s\d{4}\s\d{4})\b", text)
            if m:
                val = m.group(1)
                conf, bbox = self._find_block_details(val, blocks, 90.0)
                data["id_number"] = {"value": val, "confidence": conf, "bbox": bbox}
        elif "passport" in text_lower:
            data["id_type"] = {"value": "Passport", "confidence": 100.0, "bbox": None}
            m = re.search(r"\b([A-Z]\d{7})\b", text)
            if m:
                val = m.group(1)
                conf, bbox = self._find_block_details(val, blocks, 90.0)
                data["id_number"] = {"value": val, "confidence": conf, "bbox": bbox}

        for idx, line in enumerate(lines):
            line_lower = line.lower()
            if "name" in line_lower and "father" not in line_lower:
                m = re.search(r"name\s*[:\-]?\s*([a-zA-Z\s]+)", line, re.IGNORECASE)
                if m and len(m.group(1).strip()) > 3:
                    name = m.group(1).strip()
                    conf, bbox = self._find_block_details(name, blocks, 100.0)
                    data["name"] = {"value": name, "confidence": conf, "bbox": bbox}
                    break

        for line in lines:
            line_lower = line.lower()
            if "dob" in line_lower or "birth" in line_lower or "date of birth" in line_lower:
                m = re.search(r"(\d{2}[/\-]\d{2}[/\-]\d{4})", line)
                if m:
                    dob = m.group(1).strip()
                    conf, bbox = self._find_block_details(dob, blocks, 90.0)
                    data["dob"] = {"value": dob, "confidence": conf, "bbox": bbox}
                    break

        # Attempt to parse Address
        for idx, line in enumerate(lines):
            line_lower = line.lower()
            if "address" in line_lower or "add:" in line_lower:
                address_parts = [line]
                for offset in range(1, 4):
                    if idx + offset < len(lines):
                        next_l = lines[idx+offset]
                        if not any(k in next_l.lower() for k in ["dob", "phone", "email", "signature", "uidai"]):
                            address_parts.append(next_l)
                addr_text = " ".join(address_parts)
                conf, bbox = self._find_block_details(line, blocks, 90.0)
                data["address"] = {"value": addr_text, "confidence": conf, "bbox": bbox}
                break

        return data


class OCREngine:
    """Unified OCR pipeline for images and PDFs with entity extraction."""

    # ── Lazy singleton for EasyOCR reader ────────────────────────────
    _reader: Optional[easyocr.Reader] = None
    _reader_lock = threading.Lock()
    _reader_languages: list[str] = []

    def __init__(self, languages: list[str] | None = None):
        self.languages = languages or ["en"]
        self._ensure_reader()

    def _ensure_reader(self) -> easyocr.Reader:
        """Thread-safe lazy initialization of the EasyOCR reader."""
        if OCREngine._reader is None or OCREngine._reader_languages != self.languages:
            with OCREngine._reader_lock:
                # Double-checked locking
                if OCREngine._reader is None or OCREngine._reader_languages != self.languages:
                    logger.info(
                        "Initializing EasyOCR reader (languages={})", self.languages
                    )
                    OCREngine._reader = easyocr.Reader(
                        self.languages, gpu=False, verbose=False
                    )
                    OCREngine._reader_languages = self.languages
                    logger.info("EasyOCR reader initialized successfully")
        return OCREngine._reader

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Apply image preprocessing to improve OCR accuracy:
        1. Grayscale conversion
        2. Bilateral filtering for denoising
        3. CLAHE for contrast enhancement
        4. Unsharp mask sharpening
        """
        try:
            if image is None or image.size == 0:
                return image

            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()

            # Remove noise but keep sharp edges
            denoised = cv2.bilateralFilter(gray, 9, 75, 75)

            # CLAHE contrast enhancement
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            contrast = clahe.apply(denoised)

            # Sharpening (Unsharp Mask)
            gaussian = cv2.GaussianBlur(contrast, (0, 0), 2.0)
            sharpened = cv2.addWeighted(contrast, 1.5, gaussian, -0.5, 0)

            return sharpened
        except Exception as exc:
            logger.error("Preprocessing failed: {}", exc)
            return image

    # ── Image OCR ────────────────────────────────────────────────────
    def extract_text_from_image(self, image: np.ndarray) -> dict:
        """
        Run OCR on a NumPy image array after preprocessing.
        """
        try:
            if image is None or image.size == 0:
                logger.warning("Empty image passed to OCR engine")
                return {
                    "full_text": "",
                    "blocks": [],
                    "avg_confidence": 0.0,
                    "word_count": 0,
                }

            reader = self._ensure_reader()
            preprocessed = self.preprocess_image(image)
            with OCREngine._reader_lock:
                results = reader.readtext(preprocessed)

            blocks: list[dict] = []
            texts: list[str] = []
            img_h, img_w = preprocessed.shape[:2]

            for bbox_raw, text, confidence in results:
                xs = [int(pt[0]) for pt in bbox_raw]
                ys = [int(pt[1]) for pt in bbox_raw]
                
                # Normalize to 0-100% bounds
                x_pct = round((min(xs) / img_w) * 100.0, 3) if img_w > 0 else min(xs)
                y_pct = round((min(ys) / img_h) * 100.0, 3) if img_h > 0 else min(ys)
                w_pct = round(((max(xs) - min(xs)) / img_w) * 100.0, 3) if img_w > 0 else (max(xs) - min(xs))
                h_pct = round(((max(ys) - min(ys)) / img_h) * 100.0, 3) if img_h > 0 else (max(ys) - min(ys))

                blocks.append(
                    {
                        "text": text,
                        "confidence": round(float(confidence), 4),
                        "bbox": [x_pct, y_pct, w_pct, h_pct],
                    }
                )
                texts.append(text)

            full_text = " ".join(texts)
            avg_confidence = (
                round(
                    sum(b["confidence"] for b in blocks) / len(blocks), 4
                )
                if blocks
                else 0.0
            )
            word_count = len(full_text.split()) if full_text.strip() else 0

            logger.debug(
                "OCR extracted {} blocks, {} words, avg_conf={:.2f}",
                len(blocks),
                word_count,
                avg_confidence,
            )
            return {
                "full_text": full_text,
                "blocks": blocks,
                "avg_confidence": avg_confidence,
                "word_count": word_count,
            }

        except Exception as exc:
            logger.error("OCR image extraction failed: {}", exc)
            return {
                "full_text": "",
                "blocks": [],
                "avg_confidence": 0.0,
                "word_count": 0,
            }

    # ── PDF text extraction ──────────────────────────────────────────
    def extract_text_from_pdf(self, pdf_path: str) -> dict:
        """
        Extract text from all pages of a PDF by converting each to an image and running image-based OCR.
        """
        try:
            from app.utils.image_processing import pdf_to_images
            path = Path(pdf_path)
            if not path.exists():
                logger.error("PDF not found: {}", pdf_path)
                return {
                    "pages": [],
                    "full_text": "",
                    "total_pages": 0,
                    "avg_confidence": 0.0,
                }

            # Convert every page of the PDF into a BGR image array
            page_images = pdf_to_images(str(path))
            pages: list[dict] = []
            all_text_parts: list[str] = []
            confidences: list[float] = []

            for page_idx, img in enumerate(page_images):
                page_num = page_idx + 1
                ocr_result = self.extract_text_from_image(img)
                pages.append(
                    {
                        "page_num": page_num,
                        "text": ocr_result["full_text"],
                        "method": "ocr",
                        "blocks": ocr_result["blocks"],
                        "confidence": ocr_result["avg_confidence"],
                    }
                )
                all_text_parts.append(ocr_result["full_text"])
                confidences.append(ocr_result["avg_confidence"])

            full_text = "\n\n".join(all_text_parts)
            avg_confidence = (
                round(sum(confidences) / len(confidences), 4) if confidences else 0.0
            )

            logger.info(
                "PDF processed via OCR: {} pages, avg_confidence={:.2f}",
                len(pages),
                avg_confidence,
            )
            return {
                "pages": pages,
                "full_text": full_text,
                "total_pages": len(pages),
                "avg_confidence": avg_confidence,
            }

        except Exception as exc:
            logger.error("PDF extraction failed: {}", exc)
            return {
                "pages": [],
                "full_text": "",
                "total_pages": 0,
                "avg_confidence": 0.0,
            }

    # ── Entity extraction (regex-based) ──────────────────────────────
    def extract_entities(self, text: str) -> dict:
        """
        Extract structured entities from raw text using regex patterns.
        """
        entities: dict[str, list[str]] = {
            "amounts": [],
            "dates": [],
            "pan_numbers": [],
            "aadhaar_numbers": [],
            "account_numbers": [],
            "ifsc_codes": [],
            "phone_numbers": [],
            "email_addresses": [],
            "percentages": [],
        }

        if not text or not text.strip():
            return entities

        try:
            amount_patterns = [
                r"[₹]\s*[\d,]+(?:\.\d{1,2})?",
                r"Rs\.?\s*[\d,]+(?:\.\d{1,2})?",
                r"INR\s*[\d,]+(?:\.\d{1,2})?",
                r"\b\d{1,3}(?:,\d{2})*,\d{3}(?:\.\d{1,2})?\b",
                r"\b\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?\b",
            ]
            for pat in amount_patterns:
                entities["amounts"].extend(re.findall(pat, text))
            entities["amounts"] = list(dict.fromkeys(entities["amounts"]))

            date_patterns = [
                r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
                r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
                r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
                r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b",
                r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
            ]
            for pat in date_patterns:
                entities["dates"].extend(re.findall(pat, text, re.IGNORECASE))
            entities["dates"] = list(dict.fromkeys(entities["dates"]))

            entities["pan_numbers"] = list(dict.fromkeys(re.findall(r"\b[A-Z]{5}\d{4}[A-Z]\b", text)))
            entities["aadhaar_numbers"] = list(dict.fromkeys(re.findall(r"\b\d{4}\s\d{4}\s\d{4}\b", text)))
            entities["account_numbers"] = list(dict.fromkeys(re.findall(r"\b\d{10,18}\b", text)))
            entities["ifsc_codes"] = list(dict.fromkeys(re.findall(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", text)))

            phone_patterns = [
                r"\+91[\s-]?\d{5}[\s-]?\d{5}",
                r"\b0\d{2,4}[\s-]?\d{6,8}\b",
                r"\b[6-9]\d{9}\b",
            ]
            for pat in phone_patterns:
                entities["phone_numbers"].extend(re.findall(pat, text))
            entities["phone_numbers"] = list(dict.fromkeys(entities["phone_numbers"]))

            entities["email_addresses"] = list(dict.fromkeys(re.findall(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", text)))
            entities["percentages"] = list(dict.fromkeys(re.findall(r"\b\d+(?:\.\d+)?\s*%", text)))

        except Exception as exc:
            logger.error("Entity extraction failed: {}", exc)

        return entities

    # ── Orchestrator ─────────────────────────────────────────────────
    def process_document(self, file_path: str, file_type: str) -> dict:
        """
        High-level document processing: extract text, classify document,
        and run type-specific structured data parsing.
        """
        try:
            logger.info("Processing document: {} (type={})", file_path, file_type)
            file_type_lower = file_type.lower()

            if "pdf" in file_type_lower:
                extraction = self.extract_text_from_pdf(file_path)
            else:
                image = cv2.imread(file_path)
                if image is None:
                    logger.error("Failed to load image: {}", file_path)
                    return self._empty_result(file_path, file_type)
                extraction = self.extract_text_from_image(image)

            full_text = extraction.get("full_text", "")
            entities = self.extract_entities(full_text)

            # Aggregate all spatial blocks across pages
            all_blocks = []
            if "pages" in extraction:
                for page in extraction["pages"]:
                    p_num = page.get("page_num", 1)
                    for b in page.get("blocks", []):
                        b_copy = dict(b)
                        b_copy["page"] = p_num
                        all_blocks.append(b_copy)
            else:
                for b in extraction.get("blocks", []):
                    b_copy = dict(b)
                    b_copy["page"] = 1
                    all_blocks.append(b_copy)

            # Run Document-Type Specific Parsing
            parser = StructuredOCRParser()
            document_type = parser.classify_document(full_text)
            structured_data, field_confidences = parser.parse(full_text, all_blocks, document_type)

            # Build page-aware fields list
            page_aware_fields = []
            for key, val in structured_data.items():
                if key == "transactions":
                    continue
                if isinstance(val, dict):
                    field_name = key.replace("_", " ").title()
                    # Keep acronyms uppercase
                    if "Ifsc" in field_name:
                        field_name = field_name.replace("Ifsc", "IFSC")
                    if "Dob" in field_name:
                        field_name = field_name.replace("Dob", "DOB")
                    if "Id " in field_name:
                        field_name = field_name.replace("Id ", "ID ")
                        
                    page_aware_fields.append({
                        "page": val.get("page", 1),
                        "field": field_name,
                        "value": val.get("value"),
                        "confidence": val.get("confidence", 0.0),
                        "coordinates": val.get("bbox")
                    })

            # Determine composite OCR confidence
            ocr_conf = float(extraction.get("avg_confidence", 0.9)) * 100.0

            result = {
                "extraction": extraction,
                "entities": entities,
                "document_type": document_type,
                "structured_data": structured_data,
                "field_confidences": field_confidences,
                "ocr_confidence": ocr_conf,
                "page_aware_fields": page_aware_fields,
                "fields": page_aware_fields,
                "file_path": file_path,
                "file_type": file_type,
            }

            logger.info(
                "Document processed successfully: type={}, {} words, {} entities found. OCR Confidence: {:.1f}%",
                document_type,
                extraction.get("word_count", len(full_text.split())),
                sum(len(v) for v in entities.values()),
                ocr_conf,
            )
            return result

        except Exception as exc:
            logger.error("Document processing failed for {}: {}", file_path, exc)
            return self._empty_result(file_path, file_type)

    def _empty_result(self, file_path: str, file_type: str) -> dict:
        return {
            "extraction": {
                "full_text": "",
                "blocks": [],
                "avg_confidence": 0.0,
                "word_count": 0,
            },
            "entities": self.extract_entities(""),
            "document_type": "Unknown",
            "structured_data": {},
            "field_confidences": {},
            "ocr_confidence": 0.0,
            "page_aware_fields": [],
            "fields": [],
            "file_path": file_path,
            "file_type": file_type,
        }
