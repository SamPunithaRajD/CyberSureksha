"""
DocuShield AI — OCR Error Correction Layer
=========================================
Stablizes OCR output before fraud detection analysis. Corrects typos in bank names,
normalizes currency symbols, cleans formatting spacing inside account numbers and dates,
and removes trailing noise characters.
"""

import re
from loguru import logger

class OCRCorrectionLayer:
    """
    OCR Correction Layer runs immediately after OCR text extraction and before fraud analysis.
    Normalizes common typos, formatting quirks, and accidental noise characters.
    """
    
    VERIFIED_BANKS = [
        "State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank", 
        "Canara Bank", "Punjab National Bank", "Bank of Baroda", "Union Bank of India",
        "IDBI Bank", "IndusInd Bank", "Kotak Mahindra Bank", "Yes Bank",
        "Federal Bank", "Indian Bank", "UCO Bank", "Central Bank of India",
        "Bank of India", "Citibank", "HSBC", "Standard Chartered"
    ]
    
    def correct(self, ocr_result: dict) -> dict:
        """
        Orchestrate OCR error corrections.
        Modifies ocr_result in-place and returns it.
        """
        logger.info("Running OCR Error Correction Layer")
        if not ocr_result:
            return ocr_result
            
        # 1. Correct Currency symbols in text and blocks
        self._normalize_currency_symbols(ocr_result)
        
        # 2. Correct Bank Names
        self._correct_bank_names(ocr_result)
        
        # 3. Clean Account Numbers
        self._clean_account_numbers(ocr_result)
        
        # 4. Normalize Dates
        self._normalize_dates(ocr_result)
        
        # 5. Remove Accidental Noise Symbols from amounts
        self._clean_amount_symbols(ocr_result)
        
        return ocr_result
        
    def _normalize_currency_symbols(self, ocr_result: dict):
        """Replace common character misreads like 'I' or 'l' preceding numbers with '₹'"""
        extraction = ocr_result.get("extraction", {})
        full_text = extraction.get("full_text", "")
        if not full_text:
            return
            
        # Normalize in full_text
        text_norm = re.sub(r"\b[Ii|l]\s*(?=\d)", "₹", full_text)
        text_norm = re.sub(r"(?<=[:\s\n])[Ii|l]\s*(?=\d)", "₹", text_norm)
        extraction["full_text"] = text_norm
        
        # Normalize in blocks
        if "pages" in extraction:
            for page in extraction["pages"]:
                for block in page.get("blocks", []):
                    b_text = block.get("text", "")
                    b_norm = re.sub(r"\b[Ii|l]\s*(?=\d)", "₹", b_text)
                    b_norm = re.sub(r"(?<=[:\s\n])[Ii|l]\s*(?=\d)", "₹", b_norm)
                    block["text"] = b_norm
        else:
            for block in extraction.get("blocks", []):
                b_text = block.get("text", "")
                b_norm = re.sub(r"\b[Ii|l]\s*(?=\d)", "₹", b_text)
                b_norm = re.sub(r"(?<=[:\s\n])[Ii|l]\s*(?=\d)", "₹", b_norm)
                block["text"] = b_norm

    def _correct_bank_names(self, ocr_result: dict):
        """Correct common OCR typos in bank names."""
        structured_data = ocr_result.get("structured_data", {})
        bank_name_field = structured_data.get("bank_name")
        if not bank_name_field:
            return
            
        bank_name = bank_name_field.get("value") if isinstance(bank_name_field, dict) else bank_name_field
        if not bank_name or bank_name == "Unknown":
            return
            
        corrections = {
            "canarra bank": "Canara Bank",
            "state bnk of india": "State Bank of India",
            "state bank of ind": "State Bank of India",
            "state bnk of ind": "State Bank of India",
            "hdfc bnk": "HDFC Bank",
            "hdfc bank lted": "HDFC Bank",
            "icici bnk": "ICICI Bank",
            "axiss bank": "Axis Bank",
            "punjab natinal bank": "Punjab National Bank",
            "bnk of baroda": "Bank of Baroda"
        }
        
        det_clean = bank_name.lower().strip()
        if det_clean in corrections:
            corrected = corrections[det_clean]
            logger.info(f"Corrected Bank Name: '{bank_name}' -> '{corrected}'")
            if isinstance(bank_name_field, dict):
                bank_name_field["value"] = corrected
            else:
                structured_data["bank_name"] = corrected

    def _clean_account_numbers(self, ocr_result: dict):
        """Normalize spaces or separators in account numbers."""
        structured_data = ocr_result.get("structured_data", {})
        acc_num_field = structured_data.get("account_number")
        if not acc_num_field:
            return
            
        acc_num = acc_num_field.get("value") if isinstance(acc_num_field, dict) else acc_num_field
        if not acc_num or acc_num == "Unknown":
            return
            
        # If it's a string, strip any accidental chars from edges
        if isinstance(acc_num, str):
            cleaned = acc_num.replace(" ", "").strip()
            # If account number ends with common noise chars, strip them
            cleaned = re.sub(r"[#\*@!]$", "", cleaned)
            if cleaned != acc_num:
                logger.info(f"Cleaned Account Number: '{acc_num}' -> '{cleaned}'")
                if isinstance(acc_num_field, dict):
                    acc_num_field["value"] = cleaned
                else:
                    structured_data["account_number"] = cleaned

    def _normalize_dates(self, ocr_result: dict):
        """Normalize spaces around separators in dates, e.g. '12/ 12 / 2023' -> '12/12/2023'"""
        extraction = ocr_result.get("extraction", {})
        full_text = extraction.get("full_text", "")
        if not full_text:
            return
            
        # Replace '12/ 12 / 2023' with '12/12/2023'
        normalized = re.sub(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})", r"\1/\2/\3", full_text)
        normalized = re.sub(r"(\d{1,2})\s*-\s*([A-Za-z]+)\s*-\s*(\d{2,4})", r"\1-\2-\3", normalized)
        extraction["full_text"] = normalized
        
        # Clean dates in parsed entities
        entities = ocr_result.get("entities", {})
        if "dates" in entities:
            clean_dates = []
            for d in entities["dates"]:
                d_clean = re.sub(r"\s*/\s*", "/", d)
                d_clean = re.sub(r"\s*-\s*", "-", d_clean)
                clean_dates.append(d_clean)
            entities["dates"] = list(dict.fromkeys(clean_dates))

    def _clean_amount_symbols(self, ocr_result: dict):
        """Clean accidental trailing symbols from amounts/balances, e.g. '₹1,00,500#' -> '1,00,500'"""
        structured_data = ocr_result.get("structured_data", {})
        
        # Numeric amount keys
        amt_keys = [
            "basic_salary", "allowances", "bonus", "tax_deduction", 
            "net_salary", "gross_salary", "opening_balance", "closing_balance",
            "registration_value", "stamp_duty"
        ]
        
        for k in amt_keys:
            field = structured_data.get(k)
            if field is None:
                continue
                
            val = field.get("value") if isinstance(field, dict) else field
            if val is not None and isinstance(val, (int, float)):
                pass
            elif val and isinstance(val, str):
                cleaned = re.sub(r"[#\*@!]$", "", val.strip())
                cleaned = re.sub(r"^[^0-9]+", "", cleaned) # remove leading currency symbol
                try:
                    num_val = float(cleaned.replace(",", ""))
                    if isinstance(field, dict):
                        field["value"] = num_val
                    else:
                        structured_data[k] = num_val
                except ValueError:
                    pass
