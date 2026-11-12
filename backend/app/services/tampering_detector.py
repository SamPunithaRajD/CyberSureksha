"""
DocuShield AI — Tampering Detector Service
============================================
Image forensics pipeline for detecting document tampering using
Error Level Analysis (ELA), copy-move forgery detection, noise
inconsistency analysis, and edge discontinuity detection.
"""

import cv2
import numpy as np
from loguru import logger
from scipy import ndimage

try:
    from skimage import feature, filters as sk_filters
except ImportError:
    feature = None  # type: ignore
    sk_filters = None  # type: ignore


class TamperingDetector:
    """Multi-method document tampering / forgery detector."""

    # ── Error Level Analysis ─────────────────────────────────────────
    def error_level_analysis(
        self, image: np.ndarray, quality: int = 90
    ) -> dict:
        """
        Error Level Analysis (ELA).

        Re-compresses the image at a given JPEG quality and computes the
        absolute pixel-level difference.  Tampered regions that were last
        saved at a different quality level will show higher ELA residuals.

        Returns
        -------
        dict
            ela_score (0-100), mean_deviation, max_deviation,
            suspicious_regions [{bbox, intensity}], summary.
        """
        try:
            if image is None or image.size == 0:
                return self._empty_ela()

            # 1. Encode as JPEG at target quality
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            success, encoded = cv2.imencode(".jpg", image, encode_params)
            if not success:
                logger.warning("JPEG encoding failed in ELA")
                return self._empty_ela()

            # 2. Decode the re-compressed image
            recompressed = cv2.imdecode(
                np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR
            )

            # Ensure same shape (encoding may slightly change dimensions)
            if recompressed.shape != image.shape:
                recompressed = cv2.resize(
                    recompressed, (image.shape[1], image.shape[0])
                )

            # 3. Absolute difference
            diff = cv2.absdiff(image, recompressed).astype(np.float32)

            # 4. Amplify (scale ×15)
            amplified = np.clip(diff * 15.0, 0, 255).astype(np.uint8)

            # 5. Per-channel statistics
            mean_dev = float(np.mean(diff))
            std_dev = float(np.std(diff))
            max_dev = float(np.max(diff))

            # 6. Threshold to find suspicious regions (> 2σ above mean)
            gray_diff = cv2.cvtColor(amplified, cv2.COLOR_BGR2GRAY)
            threshold_val = min(
                255, max(30, int(mean_dev * 15 + 2 * std_dev * 15))
            )
            _, thresh = cv2.threshold(
                gray_diff, threshold_val, 255, cv2.THRESH_BINARY
            )

            # Morphological cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

            # 7. Find contours of suspicious regions
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            suspicious_regions: list[dict] = []
            min_area = max(100, image.shape[0] * image.shape[1] * 0.001)
            img_h, img_w = image.shape[:2]
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < min_area:
                    continue
                x, y, w, h = cv2.boundingRect(cnt)
                region_intensity = float(
                    np.mean(gray_diff[y : y + h, x : x + w])
                )
                x_pct = round((x / img_w) * 100.0, 3) if img_w > 0 else float(x)
                y_pct = round((y / img_h) * 100.0, 3) if img_h > 0 else float(y)
                w_pct = round((w / img_w) * 100.0, 3) if img_w > 0 else float(w)
                h_pct = round((h / img_h) * 100.0, 3) if img_h > 0 else float(h)
                suspicious_regions.append(
                    {"bbox": [x_pct, y_pct, w_pct, h_pct], "intensity": round(region_intensity, 2)}
                )

            # ELA score: normalised metric 0-100
            # Higher mean deviation + more suspicious regions → higher score
            deviation_score = min(mean_dev / 15.0 * 100, 100)
            region_score = min(len(suspicious_regions) * 10, 50)
            ela_score = round(min(deviation_score * 0.7 + region_score * 0.3, 100), 2)

            if ela_score < 25:
                summary = "ELA shows uniform compression levels — no obvious tampering."
            elif ela_score < 50:
                summary = (
                    "ELA detects minor compression inconsistencies. "
                    "Could be normal editing or mild tampering."
                )
            elif ela_score < 75:
                summary = (
                    "ELA reveals significant compression differences in "
                    f"{len(suspicious_regions)} region(s). Possible tampering."
                )
            else:
                summary = (
                    "ELA shows severe compression-level mismatches across "
                    f"{len(suspicious_regions)} region(s). High probability of tampering."
                )

            return {
                "ela_score": ela_score,
                "mean_deviation": round(mean_dev, 4),
                "max_deviation": round(max_dev, 4),
                "suspicious_regions": suspicious_regions,
                "summary": summary,
            }

        except Exception as exc:
            logger.error("ELA failed: {}", exc)
            return self._empty_ela()

    @staticmethod
    def _empty_ela() -> dict:
        return {
            "ela_score": 0.0,
            "mean_deviation": 0.0,
            "max_deviation": 0.0,
            "suspicious_regions": [],
            "summary": "ELA could not be performed.",
        }

    # ── Copy-Move Detection (ORB) ────────────────────────────────────
    def copy_move_detection(self, image: np.ndarray) -> dict:
        """
        Detect copy-move forgery using ORB keypoint matching.

        Matches within the *same* image whose keypoints are spatially
        distant (>50 px) suggest a region was cloned.
        """
        try:
            if image is None or image.size == 0:
                return self._empty_copy_move()

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Detect ORB keypoints
            orb = cv2.ORB_create(nfeatures=2000)
            keypoints, descriptors = orb.detectAndCompute(gray, None)

            if descriptors is None or len(keypoints) < 2:
                return {
                    "detected": False,
                    "num_suspicious_regions": 0,
                    "regions": [],
                    "confidence": 0.0,
                    "summary": "Insufficient keypoints for copy-move analysis.",
                }

            # Self-match using BFMatcher (Hamming)
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
            matches = bf.knnMatch(descriptors, descriptors, k=5)

            # Filter: good descriptor match but spatially distant
            suspicious_pairs: list[tuple[cv2.KeyPoint, cv2.KeyPoint]] = []
            distance_threshold = 50.0  # pixels
            hamming_threshold = 30  # descriptor distance

            for match_group in matches:
                for m in match_group:
                    if m.queryIdx == m.trainIdx:
                        continue
                    if m.distance > hamming_threshold:
                        continue
                    pt1 = keypoints[m.queryIdx].pt
                    pt2 = keypoints[m.trainIdx].pt
                    spatial_dist = np.sqrt(
                        (pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2
                    )
                    if spatial_dist > distance_threshold:
                        suspicious_pairs.append(
                            (keypoints[m.queryIdx], keypoints[m.trainIdx])
                        )

            # Cluster suspicious pairs into regions
            regions: list[dict] = []
            if suspicious_pairs:
                all_points = []
                for kp1, kp2 in suspicious_pairs:
                    all_points.append(kp1.pt)
                    all_points.append(kp2.pt)
                all_points_arr = np.array(all_points, dtype=np.float32)

                # Simple grid-based clustering
                cluster_dist = 80.0
                used = [False] * len(all_points_arr)
                for i in range(len(all_points_arr)):
                    if used[i]:
                        continue
                    cluster_pts = [all_points_arr[i]]
                    used[i] = True
                    for j in range(i + 1, len(all_points_arr)):
                        if used[j]:
                            continue
                        d = np.linalg.norm(
                            all_points_arr[i] - all_points_arr[j]
                        )
                        if d < cluster_dist:
                            cluster_pts.append(all_points_arr[j])
                            used[j] = True
                    if len(cluster_pts) >= 3:
                        pts = np.array(cluster_pts)
                        x_min, y_min = pts.min(axis=0).astype(int)
                        x_max, y_max = pts.max(axis=0).astype(int)
                        img_h, img_w = image.shape[:2]
                        x_pct = round((x_min / img_w) * 100.0, 3) if img_w > 0 else float(x_min)
                        y_pct = round((y_min / img_h) * 100.0, 3) if img_h > 0 else float(y_min)
                        w_pct = round(((x_max - x_min) / img_w) * 100.0, 3) if img_w > 0 else float(x_max - x_min)
                        h_pct = round(((y_max - y_min) / img_h) * 100.0, 3) if img_h > 0 else float(y_max - y_min)
                        regions.append(
                            {
                                "bbox": [x_pct, y_pct, w_pct, h_pct]
                            }
                        )

            detected = len(regions) > 0
            confidence = round(
                min(len(suspicious_pairs) / 50.0, 1.0) * 100, 2
            ) if suspicious_pairs else 0.0

            if not detected:
                summary = "No copy-move forgery detected."
            elif confidence < 40:
                summary = f"Possible copy-move activity in {len(regions)} region(s), low confidence."
            else:
                summary = f"Copy-move forgery likely detected in {len(regions)} region(s)."

            return {
                "detected": detected,
                "num_suspicious_regions": len(regions),
                "regions": regions,
                "confidence": confidence,
                "summary": summary,
            }

        except Exception as exc:
            logger.error("Copy-move detection failed: {}", exc)
            return self._empty_copy_move()

    @staticmethod
    def _empty_copy_move() -> dict:
        return {
            "detected": False,
            "num_suspicious_regions": 0,
            "regions": [],
            "confidence": 0.0,
            "summary": "Copy-move detection could not be performed.",
        }

    # ── Noise Analysis ───────────────────────────────────────────────
    def noise_analysis(self, image: np.ndarray) -> dict:
        """
        Block-wise noise variance analysis.

        Divides the image into an 8×8 grid and computes the Laplacian
        noise variance in each block. Blocks with significantly different
        noise levels indicate possible splicing.
        """
        try:
            if image is None or image.size == 0:
                return self._empty_noise()

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape

            grid_n = 8
            block_h = h // grid_n
            block_w = w // grid_n

            if block_h < 8 or block_w < 8:
                return {
                    "noise_score": 0.0,
                    "inconsistent_blocks": 0,
                    "total_blocks": 0,
                    "summary": "Image too small for block-wise noise analysis.",
                }

            # Compute Laplacian noise variance per block
            variances: list[float] = []
            for r in range(grid_n):
                for c in range(grid_n):
                    block = gray[
                        r * block_h : (r + 1) * block_h,
                        c * block_w : (c + 1) * block_w,
                    ]
                    laplacian = cv2.Laplacian(block, cv2.CV_64F)
                    variances.append(float(np.var(laplacian)))

            total_blocks = len(variances)
            if total_blocks == 0:
                return self._empty_noise()

            mean_var = float(np.mean(variances))
            std_var = float(np.std(variances))

            # Blocks with noise > 2σ from mean are inconsistent
            inconsistent = 0
            if std_var > 1e-6:
                for v in variances:
                    if abs(v - mean_var) > 2 * std_var:
                        inconsistent += 1

            ratio = inconsistent / total_blocks if total_blocks else 0.0
            noise_score = round(min(ratio * 200, 100), 2)  # scale up

            if noise_score < 20:
                summary = "Noise levels are consistent across the image."
            elif noise_score < 50:
                summary = (
                    f"{inconsistent}/{total_blocks} blocks show noise "
                    "inconsistencies. Minor splicing possible."
                )
            else:
                summary = (
                    f"{inconsistent}/{total_blocks} blocks have significantly "
                    "different noise levels — strong indicator of splicing."
                )

            return {
                "noise_score": noise_score,
                "inconsistent_blocks": inconsistent,
                "total_blocks": total_blocks,
                "summary": summary,
            }

        except Exception as exc:
            logger.error("Noise analysis failed: {}", exc)
            return self._empty_noise()

    @staticmethod
    def _empty_noise() -> dict:
        return {
            "noise_score": 0.0,
            "inconsistent_blocks": 0,
            "total_blocks": 0,
            "summary": "Noise analysis could not be performed.",
        }

    # ── Edge Inconsistency Analysis ──────────────────────────────────
    def edge_inconsistency_analysis(self, image: np.ndarray) -> dict:
        """
        Detect unnatural edge discontinuities that may indicate
        cut-paste boundaries using Canny edges + morphological analysis.
        """
        try:
            if image is None or image.size == 0:
                return self._empty_edge()

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # 1. Canny edge detection
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            edges = cv2.Canny(blurred, 50, 150)

            # 2. Detect unnatural straight-line segments using HoughLinesP
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=80,
                minLineLength=50,
                maxLineGap=10,
            )

            # 3. Morphological analysis for abrupt boundaries
            # Dilate edges then look for rectangular contours (cut-paste boundary artifacts)
            kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
            kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))

            horizontal_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_h)
            vertical_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel_v)

            combined = cv2.bitwise_or(horizontal_edges, vertical_edges)

            # Find contours in the combined morphological result
            contours, _ = cv2.findContours(
                combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # Filter for long, straight-ish contours (suspicious boundaries)
            suspicious_boundaries = 0
            min_perimeter = max(50, (gray.shape[0] + gray.shape[1]) * 0.05)

            for cnt in contours:
                perimeter = cv2.arcLength(cnt, closed=False)
                area = cv2.contourArea(cnt)
                if perimeter < min_perimeter:
                    continue

                # Straight boundary heuristic: low area-to-perimeter ratio
                if perimeter > 0:
                    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
                    if compactness < 0.1:  # Very elongated = likely a boundary
                        suspicious_boundaries += 1

            # Also count long straight lines
            num_long_lines = 0
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                    if length > min(gray.shape) * 0.15:
                        num_long_lines += 1

            total_suspicious = suspicious_boundaries + num_long_lines // 3
            edge_score = round(min(total_suspicious * 8, 100), 2)

            if edge_score < 20:
                summary = "Edge analysis shows no unnatural boundaries."
            elif edge_score < 50:
                summary = (
                    f"Detected {total_suspicious} potentially suspicious "
                    "edge boundaries. Minor concern."
                )
            else:
                summary = (
                    f"Detected {total_suspicious} suspicious edge "
                    "discontinuities consistent with cut-paste manipulation."
                )

            return {
                "edge_score": edge_score,
                "suspicious_boundaries": total_suspicious,
                "summary": summary,
            }

        except Exception as exc:
            logger.error("Edge analysis failed: {}", exc)
            return self._empty_edge()

    @staticmethod
    def _empty_edge() -> dict:
        return {
            "edge_score": 0.0,
            "suspicious_boundaries": 0,
            "summary": "Edge analysis could not be performed.",
        }

    # ── Composite Orchestrator ───────────────────────────────────────
    def process(self, image: np.ndarray) -> dict:
        """
        Run all four detection methods and aggregate into a composite
        result with a weighted score and unified heatmap_regions.
        """
        try:
            if image is None or image.size == 0:
                return {
                    "ela": self._empty_ela(),
                    "copy_move": self._empty_copy_move(),
                    "noise": self._empty_noise(),
                    "edge": self._empty_edge(),
                    "composite_score": 0.0,
                    "verdict": "clean",
                    "anomalies": [],
                    "summary": "No image provided for analysis.",
                    "heatmap_regions": [],
                    "confidence": 0.0,
                }

            logger.info(
                "Running tampering detection on image {}×{}",
                image.shape[1],
                image.shape[0],
            )

            ela_result = self.error_level_analysis(image)
            copy_move_result = self.copy_move_detection(image)
            noise_result = self.noise_analysis(image)
            edge_result = self.edge_inconsistency_analysis(image)

            # Weighted composite score
            composite_score = round(
                ela_result["ela_score"] * 0.35
                + copy_move_result["confidence"] * 0.25
                + noise_result["noise_score"] * 0.25
                + edge_result["edge_score"] * 0.15,
                2,
            )

            # Verdict
            if composite_score < 25:
                verdict = "clean"
            elif composite_score < 55:
                verdict = "suspicious"
            else:
                verdict = "tampered"

            # Construct Unified Heatmap Regions
            heatmap_regions = []
            
            # ELA regions
            for region in ela_result.get("suspicious_regions", []):
                bbox = region.get("bbox", [0, 0, 0, 0])
                intensity = region.get("intensity", 0)
                sev = "high" if intensity > 80 else ("medium" if intensity > 50 else "low")
                conf = min(int(intensity + 20), 99)
                heatmap_regions.append({
                    "x": bbox[0], "y": bbox[1], "width": bbox[2], "height": bbox[3],
                    "severity": sev, "label": "Compression Anomaly", "confidence": conf
                })
                
            # Copy Move regions
            for region in copy_move_result.get("regions", []):
                bbox = region.get("bbox", [0, 0, 0, 0])
                conf = int(copy_move_result.get("confidence", 85))
                heatmap_regions.append({
                    "x": bbox[0], "y": bbox[1], "width": bbox[2], "height": bbox[3],
                    "severity": "high", "label": "Duplicated Region", "confidence": conf
                })

            # Base confidence of module execution
            confidence = 95.0
            if composite_score > 55:
                # High score = high confidence that tampering exists
                confidence = float(np.clip(composite_score + 10, 0, 99.0))
            elif composite_score > 25:
                # Ambiguous = lower confidence
                confidence = 75.0

            # Collect anomalies
            anomalies: list[dict] = []
            if ela_result["ela_score"] > 65:
                anomalies.append({
                    "description": f"ELA detected minor compression variations (score: {ela_result['ela_score']})",
                    "severity": "low", "type": "ela_tampering"
                })
            if copy_move_result["detected"]:
                anomalies.append({
                    "description": f"Copy-move forgery detected in {copy_move_result['num_suspicious_regions']} region(s)",
                    "severity": "high", "type": "copy_move_forgery"
                })
            if noise_result["noise_score"] > 55:
                anomalies.append({
                    "description": f"Noise variance discrepancy (score: {noise_result['noise_score']})",
                    "severity": "low", "type": "noise_inconsistency"
                })
            if edge_result["edge_score"] > 55:
                anomalies.append({
                    "description": f"Potential edge discontinuity (score: {edge_result['edge_score']})",
                    "severity": "low", "type": "edge_inconsistency"
                })

            if not anomalies:
                summary = (
                    f"Document appears clean (score: {composite_score}/100). "
                    "No significant tampering indicators found."
                )
            else:
                summary = (
                    f"Tampering analysis verdict: {verdict.upper()} "
                    f"(score: {composite_score}/100). "
                    f"Issues found across {len(anomalies)} dimension(s)."
                )

            logger.info(
                "Tampering detection complete: verdict={}, score={}",
                verdict,
                composite_score,
            )

            return {
                "ela": ela_result,
                "copy_move": copy_move_result,
                "noise": noise_result,
                "edge": edge_result,
                "composite_score": composite_score,
                "verdict": verdict,
                "anomalies": anomalies,
                "summary": summary,
                "heatmap_regions": heatmap_regions,
                "confidence": round(confidence, 2)
            }

        except Exception as exc:
            logger.error("Tampering detection pipeline failed: {}", exc)
            return {
                "ela": self._empty_ela(),
                "copy_move": self._empty_copy_move(),
                "noise": self._empty_noise(),
                "edge": self._empty_edge(),
                "composite_score": 0.0,
                "verdict": "clean",
                "anomalies": [],
                "summary": f"Tampering detection failed: {exc}",
                "heatmap_regions": [],
                "confidence": 0.0
            }
