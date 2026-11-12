"""
DocuShield AI — Signature Verifier Service
============================================
Extracts signatures from document images, computes feature vectors,
and performs pairwise similarity comparison for forgery detection.
"""

import cv2
import numpy as np
from loguru import logger
from scipy.spatial.distance import cosine as cosine_distance
from skimage.metrics import structural_similarity


class SignatureVerifier:
    """Signature extraction, feature extraction, and verification."""

    # ── Signature Extraction ─────────────────────────────────────────
    def extract_signatures(self, image: np.ndarray) -> list[dict]:
        """
        Extract signature-like regions from a document image using
        adaptive thresholding and contour filtering heuristics.

        Returns list of dicts with bbox, cropped image, area, aspect_ratio.
        """
        try:
            if image is None or image.size == 0:
                logger.warning("Empty image passed to signature extractor")
                return []

            # Convert to grayscale
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image.copy()

            # Adaptive thresholding (Gaussian)
            binary = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=15,
                C=10,
            )

            # Invert — signatures are dark strokes on a light background
            inverted = cv2.bitwise_not(binary)

            # Morphological close to connect stroke fragments
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
            closed = cv2.morphologyEx(inverted, cv2.MORPH_CLOSE, kernel)

            # Find contours
            contours, _ = cv2.findContours(
                closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            signatures: list[dict] = []
            img_h, img_w = gray.shape

            for cnt in contours:
                area = cv2.contourArea(cnt)

                # Filter by area
                if area < 500 or area > 50000:
                    continue

                x, y, w, h = cv2.boundingRect(cnt)

                # Filter by aspect ratio
                aspect_ratio = w / h if h > 0 else 0
                if aspect_ratio < 0.3 or aspect_ratio > 5.0:
                    continue

                # Filter by solidity (contour area / convex hull area)
                hull = cv2.convexHull(cnt)
                hull_area = cv2.contourArea(hull)
                solidity = area / hull_area if hull_area > 0 else 0
                if solidity < 0.1:
                    continue

                # Extract ROI with padding
                pad = 10
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(img_w, x + w + pad)
                y2 = min(img_h, y + h + pad)

                roi = gray[y1:y2, x1:x2].copy()

                x_pct = round((x / img_w) * 100.0, 3) if img_w > 0 else float(x)
                y_pct = round((y / img_h) * 100.0, 3) if img_h > 0 else float(y)
                w_pct = round((w / img_w) * 100.0, 3) if img_w > 0 else float(w)
                h_pct = round((h / img_h) * 100.0, 3) if img_h > 0 else float(h)
                signatures.append(
                    {
                        "bbox": [x_pct, y_pct, w_pct, h_pct],
                        "image": roi,
                        "area": float(area),
                        "aspect_ratio": round(float(aspect_ratio), 3),
                    }
                )

            # Sort by area descending (largest = most likely to be the main signature)
            signatures.sort(key=lambda s: s["area"], reverse=True)

            logger.debug("Extracted {} signature candidate(s)", len(signatures))
            return signatures

        except Exception as exc:
            logger.error("Signature extraction failed: {}", exc)
            return []

    # ── Feature Computation ──────────────────────────────────────────
    def compute_signature_features(self, signature_img: np.ndarray) -> np.ndarray:
        """
        Compute a fixed-length feature vector from a signature image.

        Features:
        - 7 Hu Moments (log-transformed)
        - Pixel density ratio
        - Stroke width estimate (mean distance transform)
        - Number of contours
        - Total contour length (normalised)
        - Bounding box fill ratio
        """
        try:
            if signature_img is None or signature_img.size == 0:
                return np.zeros(12, dtype=np.float64)

            # Resize to standard dimensions
            resized = cv2.resize(signature_img, (150, 150))

            # Ensure grayscale
            if len(resized.shape) == 3:
                resized = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

            # Threshold
            _, binary = cv2.threshold(
                resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            features: list[float] = []

            # 1. Hu Moments (7 values, log-transformed)
            moments = cv2.moments(binary)
            hu = cv2.HuMoments(moments).flatten()
            # Log transform for numerical stability
            hu_log = -np.sign(hu) * np.log10(np.abs(hu) + 1e-10)
            features.extend(hu_log.tolist())  # 7 values

            # 2. Pixel density ratio
            total_pixels = binary.shape[0] * binary.shape[1]
            white_pixels = int(np.sum(binary > 0))
            density = white_pixels / total_pixels if total_pixels > 0 else 0.0
            features.append(density)  # 1 value

            # 3. Stroke width estimate (mean distance transform)
            dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
            stroke_mask = binary > 0
            stroke_width = (
                float(np.mean(dist_transform[stroke_mask]))
                if np.any(stroke_mask)
                else 0.0
            )
            features.append(stroke_width / 10.0)  # normalise, 1 value

            # 4. Contour-based features
            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            num_contours = len(contours)
            features.append(num_contours / 50.0)  # normalise, 1 value

            total_contour_length = sum(
                cv2.arcLength(c, closed=False) for c in contours
            )
            # Normalise by image perimeter
            perimeter = 2 * (150 + 150)
            features.append(
                total_contour_length / (perimeter * 5) if perimeter > 0 else 0.0
            )  # 1 value

            # 5. Bounding box fill ratio
            if contours:
                all_points = np.vstack(contours)
                rx, ry, rw, rh = cv2.boundingRect(all_points)
                bb_area = rw * rh
                fill_ratio = white_pixels / bb_area if bb_area > 0 else 0.0
            else:
                fill_ratio = 0.0
            features.append(fill_ratio)  # 1 value

            feature_vector = np.array(features, dtype=np.float64)

            # Normalise entire vector to unit length
            norm = np.linalg.norm(feature_vector)
            if norm > 1e-10:
                feature_vector = feature_vector / norm

            return feature_vector  # shape: (12,)

        except Exception as exc:
            logger.error("Feature computation failed: {}", exc)
            return np.zeros(12, dtype=np.float64)

    # ── Signature Comparison ─────────────────────────────────────────
    def compare_signatures(
        self, sig1: np.ndarray, sig2: np.ndarray
    ) -> dict:
        """
        Compare two signature images using SSIM, cosine similarity
        on feature vectors, and Hu moment distance.

        Returns similarity_score (0-100) and verdict.
        """
        try:
            if sig1 is None or sig2 is None or sig1.size == 0 or sig2.size == 0:
                return {
                    "similarity_score": 0.0,
                    "ssim": 0.0,
                    "cosine_similarity": 0.0,
                    "hu_moment_distance": float("inf"),
                    "verdict": "mismatch",
                }

            # Resize both to same dimensions
            target_size = (150, 150)

            s1 = sig1.copy()
            s2 = sig2.copy()

            if len(s1.shape) == 3:
                s1 = cv2.cvtColor(s1, cv2.COLOR_BGR2GRAY)
            if len(s2.shape) == 3:
                s2 = cv2.cvtColor(s2, cv2.COLOR_BGR2GRAY)

            s1_resized = cv2.resize(s1, target_size)
            s2_resized = cv2.resize(s2, target_size)

            # 1. SSIM
            ssim_val = float(
                structural_similarity(s1_resized, s2_resized, data_range=255)
            )

            # 2. Cosine similarity on feature vectors
            feat1 = self.compute_signature_features(s1)
            feat2 = self.compute_signature_features(s2)

            # scipy cosine returns *distance*, so similarity = 1 - distance
            cos_dist = cosine_distance(feat1, feat2)
            if np.isnan(cos_dist):
                cos_dist = 1.0
            cos_sim = 1.0 - cos_dist

            # 3. Hu moment distance (log-transformed)
            moments1 = cv2.moments(s1_resized)
            moments2 = cv2.moments(s2_resized)
            hu1 = cv2.HuMoments(moments1).flatten()
            hu2 = cv2.HuMoments(moments2).flatten()

            hu1_log = -np.sign(hu1) * np.log10(np.abs(hu1) + 1e-10)
            hu2_log = -np.sign(hu2) * np.log10(np.abs(hu2) + 1e-10)
            hu_dist = float(np.linalg.norm(hu1_log - hu2_log))

            # Convert hu_distance to a 0-1 similarity (lower distance = higher similarity)
            hu_sim = 1.0 / (1.0 + hu_dist)

            # 4. Weighted combination
            # SSIM: 0.4, Cosine: 0.35, Hu: 0.25
            raw_score = ssim_val * 0.4 + cos_sim * 0.35 + hu_sim * 0.25
            similarity_score = round(max(0.0, min(raw_score * 100, 100)), 2)

            # 5. Verdict
            if similarity_score > 80:
                verdict = "match"
            elif similarity_score > 60:
                verdict = "likely_match"
            elif similarity_score > 40:
                verdict = "mismatch"
            else:
                verdict = "forgery_suspected"

            return {
                "similarity_score": similarity_score,
                "ssim": round(ssim_val, 4),
                "cosine_similarity": round(cos_sim, 4),
                "hu_moment_distance": round(hu_dist, 4),
                "verdict": verdict,
            }

        except Exception as exc:
            logger.error("Signature comparison failed: {}", exc)
            return {
                "similarity_score": 0.0,
                "ssim": 0.0,
                "cosine_similarity": 0.0,
                "hu_moment_distance": float("inf"),
                "verdict": "mismatch",
            }

    # ── Consistency Check ────────────────────────────────────────────
    def check_signature_consistency(self, signatures: list[dict]) -> dict:
        """
        Compare all pairs of extracted signatures for consistency.
        Inconsistent signatures in the same document may indicate forgery.
        """
        try:
            num_sigs = len(signatures)

            if num_sigs < 2:
                return {
                    "num_signatures": num_sigs,
                    "comparisons": [],
                    "all_consistent": True,
                    "risk_score": 0.0,
                    "summary": (
                        "Only one or no signatures found — consistency check "
                        "requires at least two signatures."
                    ),
                }

            if num_sigs > 5:
                return {
                    "num_signatures": num_sigs,
                    "comparisons": [],
                    "all_consistent": True,
                    "risk_score": 0.0,
                    "summary": (
                        f"Bypassed consistency check: found {num_sigs} signature-like regions. "
                        "High count indicates standard printed text or tabular blocks rather than hand-written signature fields."
                    ),
                }

            comparisons: list[dict] = []
            min_similarity = 100.0

            for i in range(num_sigs):
                for j in range(i + 1, num_sigs):
                    result = self.compare_signatures(
                        signatures[i]["image"], signatures[j]["image"]
                    )
                    sim_score = result["similarity_score"]
                    comparisons.append(
                        {
                            "sig_pair": [i, j],
                            "similarity": sim_score,
                            "verdict": result["verdict"],
                        }
                    )
                    min_similarity = min(min_similarity, sim_score)

            # All consistent if minimum pairwise similarity > 50
            all_consistent = min_similarity > 50.0

            # Risk score: inverse of minimum similarity
            risk_score = round(max(0.0, 100.0 - min_similarity), 2)

            if all_consistent:
                summary = (
                    f"All {num_sigs} signatures are consistent "
                    f"(min similarity: {min_similarity:.1f}%)."
                )
            else:
                inconsistent_pairs = [
                    c for c in comparisons if c["similarity"] < 50
                ]
                summary = (
                    f"{len(inconsistent_pairs)} signature pair(s) show "
                    f"significant dissimilarity (min: {min_similarity:.1f}%). "
                    "Possible forgery or multiple signatories."
                )

            return {
                "num_signatures": num_sigs,
                "comparisons": comparisons,
                "all_consistent": all_consistent,
                "risk_score": risk_score,
                "summary": summary,
            }

        except Exception as exc:
            logger.error("Signature consistency check failed: {}", exc)
            return {
                "num_signatures": len(signatures),
                "comparisons": [],
                "all_consistent": True,
                "risk_score": 0.0,
                "summary": f"Consistency check failed: {exc}",
            }

    # ── Orchestrator ─────────────────────────────────────────────────
    def process(self, image: np.ndarray) -> dict:
        """
        Full signature analysis pipeline: extract → check consistency → report.
        """
        try:
            if image is None or image.size == 0:
                return {
                    "signatures_found": 0,
                    "signature_locations": [],
                    "consistency": {
                        "num_signatures": 0,
                        "comparisons": [],
                        "all_consistent": True,
                        "risk_score": 0.0,
                        "summary": "No image provided.",
                    },
                    "risk_score": 0.0,
                    "anomalies": [],
                    "summary": "No image provided for signature analysis.",
                }

            logger.info(
                "Running signature verification on image {}×{}",
                image.shape[1],
                image.shape[0],
            )

            # Extract signatures
            signatures = self.extract_signatures(image)
            num_found = len(signatures)
            locations = [{"bbox": s["bbox"]} for s in signatures]

            # Consistency check (needs ≥2)
            consistency = self.check_signature_consistency(signatures)

            # Anomalies
            anomalies = []
            if num_found == 0:
                anomalies.append({
                    "issue": "Missing signatures",
                    "severity": "medium",
                    "description": "No signatures detected in the document.",
                    "confidence": 0.80,
                    "recommendation": "Confirm if signature is required for this document type.",
                    "type": "missing_signature"
                })
            if not consistency["all_consistent"]:
                anomalies.append({
                    "issue": "Signature mismatch",
                    "severity": "high",
                    "description": "Signature inconsistency detected among document signatures.",
                    "confidence": 0.85,
                    "recommendation": "Perform manual signature comparison check.",
                    "type": "signature_mismatch"
                })

            risk_score = consistency["risk_score"]

            if num_found == 0:
                summary = "No signatures were detected in the document image."
            elif consistency["all_consistent"]:
                summary = (
                    f"Found {num_found} signature(s). "
                    "All signatures appear consistent."
                )
            else:
                summary = (
                    f"Found {num_found} signature(s). "
                    f"WARNING: Signature inconsistencies detected "
                    f"(risk score: {risk_score}/100)."
                )

            logger.info(
                "Signature analysis complete: {} found, risk={}",
                num_found,
                risk_score,
            )

            return {
                "signatures_found": num_found,
                "signature_locations": locations,
                "consistency": consistency,
                "risk_score": risk_score,
                "anomalies": anomalies,
                "summary": summary,
            }

        except Exception as exc:
            logger.error("Signature processing failed: {}", exc)
            return {
                "signatures_found": 0,
                "signature_locations": [],
                "consistency": {
                    "num_signatures": 0,
                    "comparisons": [],
                    "all_consistent": True,
                    "risk_score": 0.0,
                    "summary": f"Processing failed: {exc}",
                },
                "risk_score": 0.0,
                "anomalies": [f"Signature processing error: {exc}"],
                "summary": f"Signature analysis failed: {exc}",
            }
