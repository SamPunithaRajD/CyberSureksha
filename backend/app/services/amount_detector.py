"""
DocuShield AI — Amount Detector Service
=========================================
Detects and analyses financial amounts in document text for anomalies
including Benford's Law violations, suspicious round numbers, duplicates,
and statistical outliers.
"""

import math
import re
from collections import Counter
from typing import Optional

import numpy as np
from loguru import logger


class AmountDetector:
    """Financial amount extraction and anomaly analysis."""

    # ── Amount Extraction ────────────────────────────────────────────
    def extract_amounts(self, text: str) -> list[dict]:
        if not text or not text.strip():
            return []

        results: list[dict] = []
        seen_regions: list[tuple[int, int]] = []

        patterns = [
            (r"₹\s*([\d,]+(?:\.\d{1,2})?)", "INR_symbol"),
            (r"Rs\.?\s*([\d,]+(?:\.\d{1,2})?)", "INR_rs"),
            (r"INR\s*([\d,]+(?:\.\d{1,2})?)", "INR_prefix"),
            (r"\b(\d{1,2}(?:,\d{2})*,\d{3}(?:\.\d{1,2})?)\b", "indian"),
            (r"\b(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?)\b", "western"),
            (r"\b(\d{6,18}(?:\.\d{1,2})?)\b", "plain"),
        ]

        try:
            for pattern, fmt in patterns:
                for match in re.finditer(pattern, text):
                    pos = match.start()
                    end = match.end()
                    if any(max(pos, s) < min(end, e) for s, e in seen_regions):
                        continue

                    original = match.group(0)
                    numeric_str = match.group(1) if match.lastindex else original

                    cleaned = numeric_str.replace(",", "").strip()
                    try: value = float(cleaned)
                    except ValueError: continue

                    if value < 1.0: continue
                    if fmt == "plain" and len(cleaned.split('.')[0]) >= 10:
                        continue

                    results.append({"original": original.strip(), "value": value, "position": pos, "format": fmt})
                    seen_regions.append((pos, end))

            results.sort(key=lambda r: r["position"])
            logger.debug("Extracted {} monetary amounts", len(results))
        except Exception as exc:
            logger.error("Amount extraction failed: {}", exc)

        return results

    # ── Smart Financial Validation ───────────────────────────────────
    def smart_financial_validation(self, text: str, amounts: list[float], structured_data: dict = None) -> list[dict]:
        anomalies = []
        text_lower = text.lower()
        
        # 1. Structured Data Validations
        if structured_data:
            # Payslip / Salary logic
            if "basic_salary" in structured_data and structured_data["basic_salary"].get("value") != 0.0:
                basic = structured_data.get("basic_salary", {}).get("value") or 0.0
                allowances = structured_data.get("allowances", {}).get("value") or 0.0
                bonus = structured_data.get("bonus", {}).get("value") or 0.0
                deductions = structured_data.get("tax_deduction", {}).get("value") or 0.0
                net = structured_data.get("net_salary", {}).get("value") or 0.0
                gross = structured_data.get("gross_salary", {}).get("value") or 0.0
                
                if gross > 0:
                    calc_gross = basic + allowances + bonus
                    # Check basic math
                    if abs(calc_gross - gross) > 5.0:
                        anomalies.append({
                            "issue": "Salary manipulation",
                            "severity": "critical",
                            "description": f"Extracted gross salary (₹{gross:,.2f}) does not match the sum of basic, allowances, and bonus (₹{calc_gross:,.2f}).",
                            "confidence": 0.95,
                            "recommendation": "Reject application. Manipulated salary components detected.",
                            "type": "salary_manipulation",
                            "detected_value": f"Gross: {gross:,.2f}",
                            "expected_value": f"Gross (calc): {calc_gross:,.2f}",
                            "bbox": structured_data.get("gross_salary", {}).get("bbox") or structured_data.get("basic_salary", {}).get("bbox")
                        })
                    
                    # Deductions match gross - net
                    calc_net = gross - deductions
                    if abs(calc_net - net) > 5.0:
                        anomalies.append({
                            "issue": "Salary manipulation",
                            "severity": "critical",
                            "description": f"Extracted net pay (₹{net:,.2f}) does not align with gross pay (₹{gross:,.2f}) minus deductions (₹{deductions:,.2f}).",
                            "confidence": 0.98,
                            "recommendation": "Reject application. Manipulation of net/gross salary figures detected.",
                            "type": "salary_manipulation",
                            "detected_value": f"Net: {net:,.2f}",
                            "expected_value": f"Net (calc): {calc_net:,.2f}",
                            "bbox": structured_data.get("net_salary", {}).get("bbox") or structured_data.get("gross_salary", {}).get("bbox")
                        })
                    
                    # Bonus check
                    if basic > 0 and bonus > basic * 0.8:
                        anomalies.append({
                            "issue": "Unrealistic financial structures",
                            "severity": "medium",
                            "description": f"Extracted bonus (₹{bonus:,.2f}) is unrealistically high compared to basic salary (₹{basic:,.2f}).",
                            "confidence": 0.80,
                            "recommendation": "Request manual HR verify bonus parameters.",
                            "type": "unrealistic_financial_structures",
                            "detected_value": f"Bonus: {bonus:,.2f}",
                            "expected_value": f"Bonus < {basic * 0.8:,.2f}",
                            "bbox": structured_data.get("bonus", {}).get("bbox")
                        })

            # Bank Statement running balance check
            if "transactions" in structured_data and isinstance(structured_data["transactions"].get("value"), list):
                txs = structured_data["transactions"]["value"]
                if len(txs) > 1:
                    for i in range(1, len(txs)):
                        prev_tx = txs[i-1]
                        curr_tx = txs[i]
                        prev_bal = prev_tx.get("balance") or 0.0
                        curr_bal = curr_tx.get("balance") or 0.0
                        credit = curr_tx.get("credit") or 0.0
                        debit = curr_tx.get("debit") or 0.0
                        
                        expected_bal = prev_bal + credit - debit
                        if abs(expected_bal - curr_bal) > 1.0:
                            anomalies.append({
                                "issue": "Unrealistic financial structures",
                                "severity": "critical",
                                "description": f"Running transaction balance mismatch at transaction on {curr_tx.get('date')}. Expected ₹{expected_bal:,.2f} based on credit/debit, but detected ₹{curr_bal:,.2f}.",
                                "confidence": 0.98,
                                "recommendation": "Reject statement. Running balance calculation check failed.",
                                "type": "unrealistic_financial_structures",
                                "detected_value": f"Balance: {curr_bal:,.2f}",
                                "expected_value": f"Balance (calc): {expected_bal:,.2f}",
                                "bbox": curr_tx.get("bbox")
                            })
                            break

        # Fallback to Text / Regex based checks if structured data is absent
        else:
            net_pay = None
            gross_pay = None
            bonus = None
            
            net_match = re.search(r"net\s*(?:pay|salary|amount)?[\s:]*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", text_lower)
            if net_match:
                try: net_pay = float(net_match.group(1).replace(",", ""))
                except: pass
                
            gross_match = re.search(r"gross\s*(?:pay|salary|amount)?[\s:]*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", text_lower)
            if gross_match:
                try: gross_pay = float(gross_match.group(1).replace(",", ""))
                except: pass
                
            bonus_match = re.search(r"(?:performance|annual)?\s*bonus[\s:]*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", text_lower)
            if bonus_match:
                try: bonus = float(bonus_match.group(1).replace(",", ""))
                except: pass

            if net_pay and gross_pay:
                if net_pay > gross_pay:
                    anomalies.append({
                        "issue": "Salary manipulation",
                        "severity": "critical",
                        "description": f"Net pay ({net_pay:,.2f}) logically cannot exceed gross pay ({gross_pay:,.2f}).",
                        "confidence": 0.99,
                        "recommendation": "Reject application. Impossible financial math detected.",
                        "type": "salary_manipulation",
                        "detected_value": f"Net: {net_pay:,.2f}",
                        "expected_value": f"Net < {gross_pay:,.2f}",
                        "bbox": None
                    })
                    
            if bonus and gross_pay:
                if bonus > gross_pay * 0.6:
                    anomalies.append({
                        "issue": "Salary manipulation",
                        "severity": "critical",
                        "description": f"Performance bonus ({bonus:,.2f}) is unrealistically high (>60%) compared to gross pay ({gross_pay:,.2f}).",
                        "confidence": 0.85,
                        "recommendation": "Require manual HR verification of bonus payout.",
                        "type": "salary_manipulation",
                        "detected_value": f"Bonus: {bonus:,.2f}",
                        "expected_value": f"Bonus < {gross_pay * 0.6:,.2f}",
                        "bbox": None
                    })
                    
        # Rounded Amounts
        rounded_count = sum(1 for a in amounts if a >= 10000 and a % 1000 == 0)
        if len(amounts) > 5 and rounded_count > len(amounts) * 0.4:
            anomalies.append({
                "issue": "Suspicious formatting",
                "severity": "medium",
                "description": f"High proportion of perfectly rounded amounts detected ({rounded_count}/{len(amounts)}).",
                "confidence": 0.75,
                "recommendation": "Review amounts for synthetic data generation.",
                "type": "suspicious_formatting",
                "detected_value": f"Rounded: {rounded_count}",
                "expected_value": f"Rounded < {len(amounts) * 0.4:.0f}",
                "bbox": None
            })
                
        # Transaction Spikes
        if len(amounts) > 5:
            arr = np.array(amounts)
            median_val = float(np.median(arr))
            max_val = float(np.max(arr))
            if median_val > 0 and max_val > median_val * 50:
                anomalies.append({
                    "issue": "Transaction inconsistency",
                    "severity": "high",
                    "description": f"Sudden unrealistic spike detected: {max_val:,.2f} is over 50x the median amount.",
                    "confidence": 0.88,
                    "recommendation": "Investigate source of funds for the outlier transaction.",
                    "type": "transaction_inconsistency",
                    "detected_value": f"Max: {max_val:,.2f}",
                    "expected_value": f"Max < {median_val * 50:,.2f}",
                    "bbox": None
                })
                
        return anomalies

    # ── Benford's Law Analysis ───────────────────────────────────────
    def benfords_law_analysis(self, amounts: list[float]) -> dict:
        try:
            if len(amounts) < 10:
                return {"conforms_to_benfords": True, "insufficient_data": True}

            first_digits = []
            for amt in amounts:
                abs_amt = abs(amt)
                if abs_amt < 1: continue
                digit_str = str(abs_amt).lstrip("0").lstrip(".")
                if digit_str:
                    d = int(digit_str[0])
                    if 1 <= d <= 9: first_digits.append(d)

            if len(first_digits) < 10:
                return {"conforms_to_benfords": True, "insufficient_data": True}

            n = len(first_digits)
            counts = Counter(first_digits)
            expected = {d: math.log10(1 + 1 / d) for d in range(1, 10)}

            chi_sq = 0.0
            for d in range(1, 10):
                obs_count = counts.get(d, 0)
                exp_count = expected[d] * n
                if exp_count > 0:
                    chi_sq += (obs_count - exp_count) ** 2 / exp_count

            p_value = 0.05 if chi_sq > 15.507 else 0.5
            return {"conforms_to_benfords": p_value > 0.05, "insufficient_data": False}
        except:
            return {"conforms_to_benfords": True, "insufficient_data": True}

    # ── Orchestrator ─────────────────────────────────────────────────
    def process(self, text: str, structured_data: dict = None) -> dict:
        try:
            normalized_text = text
            normalized_text = re.sub(r"\b[Ii|l]\s*(?=\d)", "₹", normalized_text)
            normalized_text = re.sub(r"(?<=[:\s\n])[Ii|l]\s*(?=\d)", "₹", normalized_text)

            amount_dicts = self.extract_amounts(normalized_text)
            values = [a["value"] for a in amount_dicts]

            anomalies = self.smart_financial_validation(normalized_text, values, structured_data)
            benfords = self.benfords_law_analysis(values)
            
            if not benfords.get("insufficient_data") and not benfords["conforms_to_benfords"]:
                 anomalies.append({
                    "issue": "Transaction inconsistency",
                    "severity": "medium",
                    "description": "Amounts violate Benford's Law distribution, indicating possible fabricated numbers.",
                    "confidence": 0.80,
                    "recommendation": "Review transaction history for synthetic entries.",
                    "type": "benfords_law_violation",
                    "detected_value": "Non-conforming",
                    "expected_value": "Benford Distribution",
                    "bbox": None
                })

            # Check duplicates manually
            if values:
                counts = Counter(values)
                exact_duplicates = [val for val, cnt in counts.items() if cnt > 3 and val > 1000]
                if exact_duplicates:
                    anomalies.append({
                        "issue": "Duplicate regions",
                        "severity": "high",
                        "description": f"Found highly repeated large amounts (e.g., {exact_duplicates[0]}). May indicate copy-paste forgery.",
                        "confidence": 0.85,
                        "recommendation": "Examine document for visual repetition.",
                        "type": "duplicate_regions",
                        "detected_value": f"Duplicate: {exact_duplicates[0]:,.2f}",
                        "expected_value": "Unique transaction values",
                        "bbox": None
                    })

            risk_score = 0.0
            if anomalies:
                risk_score = min(sum(20 for a in anomalies if a["severity"] == "high") + sum(40 for a in anomalies if a["severity"] == "critical"), 100.0)

            return {
                "amounts_found": amount_dicts,
                "risk_score": risk_score,
                "anomalies": anomalies,
            }
        except Exception as exc:
            logger.error("Amount processing failed: {}", exc)
            return {"amounts_found": [], "risk_score": 0.0, "anomalies": []}
