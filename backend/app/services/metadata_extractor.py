"""
DocuShield AI — Metadata Extractor Service
============================================
Extracts and forensically analyses document metadata from PDFs and images.
Flags anomalies that may indicate tampering, forgery, or injection attacks.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import fitz  # PyMuPDF
import pikepdf
from loguru import logger
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

try:
    from dateutil import parser as date_parser
except ImportError:
    date_parser = None  # graceful fallback


# ── Suspicious software lists ────────────────────────────────────────
EDITING_SOFTWARE = {
    "photoshop",
    "gimp",
    "paint.net",
    "affinity",
    "pixlr",
    "corel",
    "inkscape",
    "illustrator",
    "canva",
    "foxit phantompdf",
    "nitro pro",
    "pdfelement",
    "adobe acrobat",
}

SCANNER_SOFTWARE = {
    "scanner",
    "scan",
    "epson",
    "canon",
    "hp scan",
    "brother",
    "twain",
    "wia",
}


class MetadataExtractor:
    """Extract and analyse metadata from PDF and image documents."""

    # ── Helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _parse_date(raw: Any) -> Optional[str]:
        """Best-effort date string parsing → ISO-8601 string."""
        if raw is None:
            return None
        try:
            raw_str = str(raw).strip()
            if not raw_str:
                return None
            # PyMuPDF format: "D:20230415120000+05'30'"
            if raw_str.startswith("D:"):
                raw_str = raw_str[2:]
                # Remove timezone quoting
                raw_str = raw_str.replace("'", "")
            if date_parser:
                dt = date_parser.parse(raw_str, fuzzy=True)
            else:
                # Fallback: try common formats
                for fmt in (
                    "%Y%m%d%H%M%S%z",
                    "%Y%m%d%H%M%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d",
                ):
                    try:
                        dt = datetime.strptime(raw_str[:len(fmt)], fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return raw_str  # Return raw if we can't parse
            return dt.isoformat()
        except Exception:
            return str(raw)

    @staticmethod
    def _safe_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        s = str(value).strip()
        return s if s else None

    # ── PDF metadata extraction ──────────────────────────────────────
    def extract_pdf_metadata(self, file_path: str) -> dict:
        """
        Extract comprehensive metadata from a PDF using PyMuPDF + pikepdf.
        """
        metadata: dict[str, Any] = {
            "title": None,
            "author": None,
            "creator": None,
            "producer": None,
            "creation_date": None,
            "modification_date": None,
            "page_count": 0,
            "file_size": 0,
            "pdf_version": None,
            "is_encrypted": False,
            "has_javascript": False,
            "has_embedded_files": False,
            "form_fields_count": 0,
        }

        path = Path(file_path)
        if not path.exists():
            logger.error("PDF not found: {}", file_path)
            return metadata

        try:
            metadata["file_size"] = path.stat().st_size

            # ── PyMuPDF extraction ───────────────────────────────────
            doc = fitz.open(str(path))
            meta = doc.metadata or {}

            metadata["title"] = self._safe_str(meta.get("title"))
            metadata["author"] = self._safe_str(meta.get("author"))
            metadata["creator"] = self._safe_str(meta.get("creator"))
            metadata["producer"] = self._safe_str(meta.get("producer"))
            metadata["creation_date"] = self._parse_date(meta.get("creationDate"))
            metadata["modification_date"] = self._parse_date(meta.get("modDate"))
            metadata["page_count"] = len(doc)
            metadata["is_encrypted"] = doc.is_encrypted

            # Check for JavaScript
            has_js = False
            for page_num in range(len(doc)):
                page = doc[page_num]
                # Check page-level JS actions via widget annotations
                for annot in page.annots() or []:
                    info = annot.info
                    if info and "javascript" in str(info).lower():
                        has_js = True
                        break
                if has_js:
                    break

            # Check document-level JS in names dict
            try:
                js_catalog = doc.pdf_catalog()
                if js_catalog:
                    xref_data = doc.xref_object(js_catalog)
                    if "JavaScript" in str(xref_data):
                        has_js = True
            except Exception:
                pass

            metadata["has_javascript"] = has_js

            # Count form fields
            form_count = 0
            for page_num in range(len(doc)):
                page = doc[page_num]
                widgets = page.widgets()
                if widgets:
                    for _ in widgets:
                        form_count += 1
            metadata["form_fields_count"] = form_count

            doc.close()

            # ── pikepdf extraction (additional fields) ───────────────
            try:
                pdf = pikepdf.open(str(path))
                metadata["pdf_version"] = pdf.pdf_version

                # Overwrite dates from pikepdf if available (more reliable)
                docinfo = pdf.docinfo
                if docinfo:
                    if "/CreationDate" in docinfo:
                        parsed = self._parse_date(str(docinfo["/CreationDate"]))
                        if parsed:
                            metadata["creation_date"] = parsed
                    if "/ModDate" in docinfo:
                        parsed = self._parse_date(str(docinfo["/ModDate"]))
                        if parsed:
                            metadata["modification_date"] = parsed
                    if "/Creator" in docinfo and not metadata["creator"]:
                        metadata["creator"] = self._safe_str(str(docinfo["/Creator"]))
                    if "/Producer" in docinfo and not metadata["producer"]:
                        metadata["producer"] = self._safe_str(str(docinfo["/Producer"]))

                # Check for embedded files
                root = pdf.Root
                if "/Names" in root:
                    names = root["/Names"]
                    if "/EmbeddedFiles" in names:
                        metadata["has_embedded_files"] = True

                # Double-check JavaScript via pikepdf
                if "/Names" in root:
                    names = root["/Names"]
                    if "/JavaScript" in names:
                        metadata["has_javascript"] = True

                pdf.close()
            except Exception as exc:
                logger.debug("pikepdf extraction partial failure: {}", exc)

        except Exception as exc:
            logger.error("PDF metadata extraction failed: {}", exc)

        return metadata

    # ── Image metadata extraction ────────────────────────────────────
    def extract_image_metadata(self, file_path: str) -> dict:
        """Extract EXIF and basic metadata from an image via Pillow."""
        metadata: dict[str, Any] = {
            "camera_make": None,
            "camera_model": None,
            "software": None,
            "datetime_original": None,
            "datetime_digitized": None,
            "gps_info": None,
            "image_width": None,
            "image_height": None,
            "color_space": None,
            "bits_per_sample": None,
            "compression": None,
        }

        path = Path(file_path)
        if not path.exists():
            logger.error("Image not found: {}", file_path)
            return metadata

        try:
            img = Image.open(str(path))
            metadata["image_width"] = img.width
            metadata["image_height"] = img.height
            metadata["color_space"] = img.mode

            # Attempt EXIF extraction
            exif_data = img.getexif()
            if not exif_data:
                logger.debug("No EXIF data in {}", file_path)
                img.close()
                return metadata

            decoded_exif: dict[str, Any] = {}
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                try:
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", errors="replace")
                    decoded_exif[tag_name] = value
                except Exception:
                    decoded_exif[tag_name] = str(value)

            metadata["camera_make"] = self._safe_str(decoded_exif.get("Make"))
            metadata["camera_model"] = self._safe_str(decoded_exif.get("Model"))
            metadata["software"] = self._safe_str(decoded_exif.get("Software"))
            metadata["datetime_original"] = self._parse_date(
                decoded_exif.get("DateTimeOriginal")
            )
            metadata["datetime_digitized"] = self._parse_date(
                decoded_exif.get("DateTimeDigitized")
            )
            metadata["bits_per_sample"] = decoded_exif.get("BitsPerSample")
            metadata["compression"] = decoded_exif.get("Compression")

            # GPS info
            gps_raw = decoded_exif.get("GPSInfo")
            if gps_raw and isinstance(gps_raw, dict):
                gps_decoded: dict[str, Any] = {}
                for gps_tag_id, gps_value in gps_raw.items():
                    gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                    gps_decoded[gps_tag_name] = str(gps_value)
                metadata["gps_info"] = gps_decoded

            img.close()

        except Exception as exc:
            logger.error("Image metadata extraction failed: {}", exc)

        return metadata

    # ── Anomaly analysis ─────────────────────────────────────────────
    def analyze_metadata_anomalies(self, metadata: dict, file_type: str) -> dict:
        """
        Inspect extracted metadata for forensic red flags.

        Returns dict with ``anomalies`` list and ``risk_score`` (0-100).
        """
        anomalies: list[dict] = []

        try:
            now = datetime.now(timezone.utc)

            # ── Date anomalies ───────────────────────────────────────
            creation = metadata.get("creation_date")
            modification = metadata.get("modification_date")

            if creation and modification:
                try:
                    c_dt = date_parser.parse(creation) if date_parser else datetime.fromisoformat(creation)
                    m_dt = date_parser.parse(modification) if date_parser else datetime.fromisoformat(modification)
                    if c_dt > m_dt:
                        anomalies.append(
                            {
                                "type": "creation_after_modification",
                                "severity": "high",
                                "description": (
                                    f"Creation date ({creation}) is after modification "
                                    f"date ({modification}). This is physically impossible "
                                    "and suggests metadata manipulation."
                                ),
                                "confidence": 0.9,
                            }
                        )
                except Exception:
                    pass

            if creation:
                try:
                    c_dt = date_parser.parse(creation) if date_parser else datetime.fromisoformat(creation)
                    if c_dt.replace(tzinfo=None) > now.replace(tzinfo=None):
                        anomalies.append(
                            {
                                "type": "future_creation_date",
                                "severity": "critical",
                                "description": (
                                    f"Creation date ({creation}) is in the future. "
                                    "Document metadata has been forged."
                                ),
                                "confidence": 0.95,
                            }
                        )
                except Exception:
                    pass

            # ── Software anomalies ───────────────────────────────────
            creator = (metadata.get("creator") or "").lower()
            producer = (metadata.get("producer") or "").lower()
            software = (metadata.get("software") or "").lower()

            # Creator/producer mismatch
            if creator and producer:
                creator_is_scanner = any(s in creator for s in SCANNER_SOFTWARE)
                producer_is_editor = any(s in producer for s in EDITING_SOFTWARE)
                if creator_is_scanner and producer_is_editor:
                    anomalies.append(
                        {
                            "type": "creator_producer_mismatch",
                            "severity": "high",
                            "description": (
                                f"Document created by scanner-like tool ('{metadata.get('creator')}') "
                                f"but produced/modified by editing software ('{metadata.get('producer')}'). "
                                "This suggests post-scan editing."
                            ),
                            "confidence": 0.85,
                        }
                    )

            # Editing software in any field
            all_sw = f"{creator} {producer} {software}"
            detected_editors = [sw for sw in EDITING_SOFTWARE if sw in all_sw]
            if detected_editors:
                anomalies.append(
                    {
                        "type": "editing_software_detected",
                        "severity": "medium",
                        "description": (
                            f"Image/document editing software detected: {', '.join(detected_editors)}. "
                            "This may indicate content modification."
                        ),
                        "confidence": 0.7,
                    }
                )

            # ── PDF-specific anomalies ───────────────────────────────
            if "pdf" in file_type.lower():
                if metadata.get("has_javascript"):
                    anomalies.append(
                        {
                            "type": "javascript_present",
                            "severity": "critical",
                            "description": (
                                "PDF contains JavaScript. This is a potential "
                                "code injection or exploitation vector."
                            ),
                            "confidence": 0.95,
                        }
                    )

                if metadata.get("has_embedded_files"):
                    anomalies.append(
                        {
                            "type": "embedded_files_present",
                            "severity": "high",
                            "description": (
                                "PDF contains embedded files. These could harbour "
                                "malware or hidden forged documents."
                            ),
                            "confidence": 0.8,
                        }
                    )

            # ── Image-specific anomalies ─────────────────────────────
            if "pdf" not in file_type.lower():
                # GPS in scanned documents is suspicious
                if metadata.get("gps_info"):
                    anomalies.append(
                        {
                            "type": "gps_in_scanned_document",
                            "severity": "medium",
                            "description": (
                                "GPS coordinates found in document image. Genuine "
                                "scanned documents typically lack GPS metadata."
                            ),
                            "confidence": 0.65,
                        }
                    )

            # ── Stripped / empty metadata ────────────────────────────
            important_fields = [
                "title", "author", "creator", "producer",
                "creation_date", "modification_date",
            ]
            empty_count = sum(
                1 for f in important_fields if not metadata.get(f)
            )
            if empty_count >= 5:
                anomalies.append(
                    {
                        "type": "metadata_stripped",
                        "severity": "medium",
                        "description": (
                            f"{empty_count}/{len(important_fields)} key metadata fields "
                            "are empty. Metadata may have been intentionally stripped "
                            "to hide provenance."
                        ),
                        "confidence": 0.6,
                    }
                )

            # ── Multiple modification tools ──────────────────────────
            tools_mentioned: set[str] = set()
            for field_val in [creator, producer, software]:
                for editor in EDITING_SOFTWARE:
                    if editor in field_val:
                        tools_mentioned.add(editor)
            if len(tools_mentioned) >= 2:
                anomalies.append(
                    {
                        "type": "multiple_tools_detected",
                        "severity": "high",
                        "description": (
                            f"Multiple editing tools detected in metadata: "
                            f"{', '.join(tools_mentioned)}. This suggests the document "
                            "passed through several editing stages."
                        ),
                        "confidence": 0.8,
                    }
                )

        except Exception as exc:
            logger.error("Anomaly analysis failed: {}", exc)

        # ── Compute risk score ───────────────────────────────────────
        severity_weights = {
            "critical": 30,
            "high": 20,
            "medium": 12,
            "low": 5,
        }
        raw_score = sum(
            severity_weights.get(a["severity"], 5) * a["confidence"]
            for a in anomalies
        )
        risk_score = round(min(raw_score, 100.0), 2)

        return {"anomalies": anomalies, "risk_score": risk_score}

    # ── Orchestrator ─────────────────────────────────────────────────
    def process(self, file_path: str, file_type: str) -> dict:
        """
        Full metadata extraction + anomaly analysis pipeline.

        Returns dict with raw_metadata, anomalies, risk_score, summary.
        """
        try:
            logger.info("Extracting metadata: {} (type={})", file_path, file_type)

            if "pdf" in file_type.lower():
                raw_metadata = self.extract_pdf_metadata(file_path)
            else:
                raw_metadata = self.extract_image_metadata(file_path)

            analysis = self.analyze_metadata_anomalies(raw_metadata, file_type)

            anomalies = analysis["anomalies"]
            risk_score = analysis["risk_score"]

            # Build human-readable summary
            if not anomalies:
                summary = "No metadata anomalies detected. Document metadata appears consistent."
            else:
                severity_counts: dict[str, int] = {}
                for a in anomalies:
                    severity_counts[a["severity"]] = (
                        severity_counts.get(a["severity"], 0) + 1
                    )
                parts = [f"{v} {k}" for k, v in severity_counts.items()]
                summary = (
                    f"Found {len(anomalies)} metadata anomalies "
                    f"({', '.join(parts)}). Risk score: {risk_score}/100."
                )

            result = {
                "raw_metadata": raw_metadata,
                "anomalies": anomalies,
                "risk_score": risk_score,
                "summary": summary,
            }

            logger.info(
                "Metadata analysis complete: {} anomalies, risk={}",
                len(anomalies),
                risk_score,
            )
            return result

        except Exception as exc:
            logger.error("Metadata processing failed for {}: {}", file_path, exc)
            return {
                "raw_metadata": {},
                "anomalies": [],
                "risk_score": 0.0,
                "summary": f"Metadata extraction failed: {exc}",
            }
