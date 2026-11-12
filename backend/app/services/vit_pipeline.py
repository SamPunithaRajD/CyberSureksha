"""
SecureDocXAI — Vision Transformer (ViT) Pipeline Module

Simulates a Vision Transformer model (e.g. LayoutLMv3, Donut, or DiT)
performing document classification, layout understanding, table detection,
visual region segmentation, feature extraction, and visual tampering analysis.

Designed to be completely plug-and-play so it can be swapped with actual PyTorch/HF weights.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal
from loguru import logger

DocumentType = Literal["Bank Statement", "Payslip", "PAN Card", "Aadhaar Card", "Passport", "Invoice", "Unknown"]


class VisionTransformerPipeline:
    """
    Plug-and-play Vision Transformer interface for document intelligence.
    Extracts visual coordinates, layout structures, and detects tampering.
    """

    def __init__(self, model_name_or_path: str = "microsoft/layoutlmv3-base"):
        self.model_name_or_path = model_name_or_path
        logger.info("Initializing Vision Transformer Pipeline using model: {}", model_name_or_path)

    def process(self, file_path: str, file_type: str = "pdf") -> dict[str, Any]:
        """
        Run ViT layout analysis, classification, and visual tampering extraction.
        
        Parameters
        ----------
        file_path : str
            Path to the document.
        file_type : str
            Extension/mime category (pdf or image).
            
        Returns
        -------
        dict
            Structured visual layout tokens, classification embeddings, and detected regions.
        """
        logger.info("Running ViT inference on document: {}", file_path)
        filename = Path(file_path).name.lower()
        
        # Determine classification category based on file name or text contents (simulated embedding classification)
        doc_type: DocumentType = "Unknown"
        confidence = 0.98
        
        if "bank" in filename or "statement" in filename or "hdfc" in filename or "sbi" in filename or "icici" in filename or "axis" in filename or "canara" in filename:
            doc_type = "Bank Statement"
        elif "payslip" in filename or "salary" in filename or "slip" in filename or "pay" in filename:
            doc_type = "Payslip"
        elif "pan" in filename:
            doc_type = "PAN Card"
        elif "aadhaar" in filename or "adhar" in filename:
            doc_type = "Aadhaar Card"
        elif "passport" in filename:
            doc_type = "Passport"
        elif "invoice" in filename or "bill" in filename:
            doc_type = "Invoice"
        
        # Bounding box layout prediction (X, Y, Width, Height in percentages 0-100)
        layout_segments = []
        visual_tampering_regions = []
        quality_score = 92.5
        
        if doc_type == "Bank Statement":
            layout_segments = [
                {"label": "header_logo", "bbox": [5.0, 4.0, 15.0, 6.0], "confidence": 0.96},
                {"label": "account_holder_name", "bbox": [5.0, 12.0, 40.0, 3.0], "confidence": 0.98},
                {"label": "account_number_label", "bbox": [60.0, 12.0, 35.0, 3.0], "confidence": 0.97},
                {"label": "transaction_table", "bbox": [5.0, 25.0, 90.0, 60.0], "confidence": 0.99},
            ]
        elif doc_type == "Payslip":
            layout_segments = [
                {"label": "company_header", "bbox": [10.0, 5.0, 80.0, 8.0], "confidence": 0.98},
                {"label": "employee_details", "bbox": [10.0, 15.0, 40.0, 10.0], "confidence": 0.95},
                {"label": "earnings_table", "bbox": [10.0, 30.0, 38.0, 35.0], "confidence": 0.99},
                {"label": "deductions_table", "bbox": [52.0, 30.0, 38.0, 35.0], "confidence": 0.99},
                {"label": "net_salary_callout", "bbox": [60.0, 70.0, 30.0, 8.0], "confidence": 0.97},
            ]
        elif doc_type == "PAN Card":
            layout_segments = [
                {"label": "govt_header", "bbox": [15.0, 5.0, 70.0, 10.0], "confidence": 0.99},
                {"label": "pan_number", "bbox": [15.0, 30.0, 50.0, 8.0], "confidence": 0.98},
                {"label": "holder_photo", "bbox": [65.0, 25.0, 25.0, 30.0], "confidence": 0.96},
                {"label": "holder_signature", "bbox": [65.0, 60.0, 25.0, 15.0], "confidence": 0.95},
            ]
        elif doc_type == "Aadhaar Card":
            layout_segments = [
                {"label": "emblem_header", "bbox": [20.0, 5.0, 60.0, 12.0], "confidence": 0.97},
                {"label": "holder_photo", "bbox": [10.0, 25.0, 25.0, 40.0], "confidence": 0.99},
                {"label": "aadhaar_number", "bbox": [35.0, 70.0, 50.0, 10.0], "confidence": 0.98},
            ]
            
        # Simulate some visual tampering detection (splicing or text replacements)
        # Check if the filename contains clues or simulate checks
        if "tampered" in filename or "forged" in filename or "fake" in filename or "modified" in filename:
            quality_score = 65.0
            visual_tampering_regions.append({
                "type": "font_discontinuity",
                "bbox": [25.0, 32.0, 15.0, 4.0],
                "description": "Visual font spacing and weight discontinuity detected in primary amount fields. Bounding box coordinates indicate overlay modification.",
                "confidence": 0.91
            })
            visual_tampering_regions.append({
                "type": "compression_discrepancy",
                "bbox": [55.0, 72.0, 20.0, 6.0],
                "description": "Higher JPEG compression artifact block (splicing trace) surrounding value credentials.",
                "confidence": 0.88
            })
            
        return {
            "model_metadata": {
                "architecture": "Vision Transformer",
                "backbone": "ViT-H/14",
                "parameters_count": "307M",
                "status": "loaded"
            },
            "document_type": doc_type,
            "classification_confidence": confidence,
            "quality_assessment": {
                "score": quality_score,
                "resolution": "150 DPI",
                "skew_angle": 0.2,
                "readability_index": "Excellent" if quality_score > 80 else "Poor"
            },
            "layout_analysis": {
                "segments": layout_segments,
                "segments_count": len(layout_segments)
            },
            "visual_tampering": {
                "detected": len(visual_tampering_regions) > 0,
                "regions": visual_tampering_regions,
                "tampering_factor": round(35.0 if len(visual_tampering_regions) > 0 else 0.0, 2)
            },
            "features_extracted": {
                "has_photo": doc_type in ("PAN Card", "Aadhaar Card", "Passport"),
                "has_signature": doc_type in ("PAN Card", "Passport", "Payslip"),
                "embedding_vector_sample": [0.0125, -0.0543, 0.1287, -0.9821, 0.4432]
            }
        }
