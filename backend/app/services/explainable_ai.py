"""
Explainable AI — Generate human-readable explanations for fraud analysis results.
Produces structured factor breakdowns, natural-language narratives, and
actionable recommendations suitable for underwriter reports.
"""

from collections import Counter
from loguru import logger


class ExplainableAI:
    """Transform raw analysis results into understandable explanations."""

    # Canonical severity ordering
    SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    # ------------------------------------------------------------------ #
    #  Main entry point
    # ------------------------------------------------------------------ #
    def generate_explanation(
        self,
        risk_score: dict,
        metadata_result: dict,
        tampering_result: dict,
        signature_result: dict,
        amount_result: dict,
        anomaly_result: dict,
    ) -> dict:
        """
        Build a structured, human-readable explanation of the fraud analysis.
        """
        logger.info("Generating explainable AI report")

        # 1. Collect ALL anomalies
        all_anomalies = self._collect_all_anomalies(
            metadata_result, tampering_result, signature_result,
            amount_result, anomaly_result,
        )

        # 2. Sort by severity then confidence (descending)
        all_anomalies.sort(
            key=lambda a: (
                self.SEVERITY_ORDER.get(a.get("severity", "low"), 99),
                -(a.get("confidence", 0)),
            )
        )

        # 3. Anomaly severity counts
        anomaly_count = self._count_severities(all_anomalies)

        # 4. Factors
        factors = self._build_factors(
            risk_score, metadata_result, tampering_result,
            signature_result, amount_result, anomaly_result, all_anomalies,
        )

        # 5. Summary and Status
        composite = risk_score.get("composite", 0)
        tier = risk_score.get("tier", "review")
        confidence = risk_score.get("analysis_confidence", 90.0)
        
        status_mapping = {
            "verified": "VERIFIED",
            "low_risk": "SAFE TO PROCESS",
            "review": "UNDER REVIEW",
            "high_risk": "REJECTED" # Will be "FRAUD SUSPECTED" or "REJECTED" based on composite
        }
        document_status = status_mapping.get(tier, "UNDER REVIEW")
        if tier == "high_risk" and composite < 85:
            document_status = "FRAUD SUSPECTED"

        summary = self._generate_summary(composite, tier, confidence, anomaly_count, all_anomalies)
        executive_summary = self._generate_executive_summary(composite, tier, all_anomalies)
        risk_in_words = self._risk_in_words(composite, tier, all_anomalies)
        recommended_actions = self._recommended_actions(composite, tier, risk_score, all_anomalies)
        narrative = self._generate_narrative(
            composite, tier, confidence, risk_score, metadata_result, tampering_result,
            signature_result, amount_result, anomaly_result, all_anomalies,
        )

        explanation = {
            "summary": summary,
            "executive_summary": executive_summary,
            "document_status": document_status,
            "risk_in_words": risk_in_words,
            "factors": factors,
            "recommended_actions": recommended_actions,
            "narrative": narrative,
            "anomaly_count": anomaly_count,
        }

        logger.info(f"Explanation generated — {len(factors)} factor(s), {sum(anomaly_count.values())} total anomalies")
        return explanation

    # ------------------------------------------------------------------ #
    #  Anomaly collection
    # ------------------------------------------------------------------ #
    def _collect_all_anomalies(self, metadata_result, tampering_result, signature_result, amount_result, anomaly_result) -> list[dict]:
        anomalies: list[dict] = []

        def _add(source_list, source_name):
            for a in source_list:
                if isinstance(a, dict):
                    anomalies.append({**a, "_source": source_name})
                elif isinstance(a, str):
                    anomalies.append({"description": a, "severity": "medium", "_source": source_name})

        _add(metadata_result.get("anomalies", []), "metadata")
        _add(tampering_result.get("anomalies", []), "tampering")
        _add(signature_result.get("anomalies", []), "signature")
        _add(amount_result.get("anomalies", []), "amount")

        for key in ("text_anomalies", "cross_field_anomalies", "pattern_anomalies"):
            _add(anomaly_result.get(key, []), "anomaly_detector")

        return anomalies

    @staticmethod
    def _count_severities(anomalies: list[dict]) -> dict:
        counts = Counter(a.get("severity", "low") for a in anomalies)
        return {
            "critical": counts.get("critical", 0),
            "high": counts.get("high", 0),
            "medium": counts.get("medium", 0),
            "low": counts.get("low", 0),
        }

    # ------------------------------------------------------------------ #
    #  Factors
    # ------------------------------------------------------------------ #
    def _build_factors(self, risk_score, metadata_result, tampering_result, signature_result, amount_result, anomaly_result, all_anomalies) -> list[dict]:
        factors: list[dict] = []
        sub_scores = risk_score.get("sub_scores", {})
        
        detected_issues = risk_score.get("detected_issues", [])
        
        # Pull factors from the final detected issues
        for issue in detected_issues:
            factors.append({
                "factor": issue["issue"],
                "impact": "negative",
                "confidence": "high" if issue["confidence"] > 90 else "medium",
                "evidence": f"{issue['recommendation']} (Severity: {issue['severity']})",
            })

        # Add explicit clean factor if score is low
        if risk_score.get("tier") in ("verified", "low_risk") and not detected_issues:
            factors.append({
                "factor": "No Significant Risk Indicators",
                "impact": "positive",
                "confidence": "high",
                "evidence": "All automated intelligence checks passed. Document appears authentic.",
            })

        # Tampering
        tampering_score = sub_scores.get("tampering", 0)
        if tampering_score > 10:
            verdict = tampering_result.get("verdict", "unknown")
            factors.append({
                "factor": "Image Tampering Analysis",
                "impact": "negative",
                "confidence": "high",
                "evidence": f"Tampering detection returned verdict '{verdict}' with score {tampering_score:.1f}/100. {tampering_result.get('summary', '')}",
            })

        # Anomaly detector
        anomaly_score = sub_scores.get("anomaly", 0)
        if anomaly_score > 10:
            factors.append({
                "factor": "Cross-Document / Pattern Anomaly",
                "impact": "negative",
                "confidence": "medium",
                "evidence": anomaly_result.get("summary", "Statistical anomalies found."),
            })

        if not factors:
            factors.append({
                "factor": "No Significant Risk Indicators",
                "impact": "positive",
                "confidence": "high",
                "evidence": "All analysis modules returned scores within acceptable thresholds.",
            })

        return factors

    # ------------------------------------------------------------------ #
    #  Summary
    # ------------------------------------------------------------------ #
    def _generate_summary(self, composite: float, tier: str, confidence: float, anomaly_count: dict, all_anomalies: list[dict]) -> str:
        total = sum(anomaly_count.values())
        tier_label = tier.replace("_", " ").upper()

        opening = f"This document received a {tier_label} risk score of {composite:.1f}/100 (Analysis Confidence: {confidence:.1f}%)."
        
        if total == 0:
            detail = "No anomalies were identified across any analysis dimension."
        else:
            critical_high = anomaly_count["critical"] + anomaly_count["high"]
            if critical_high > 0:
                detail = f"{total} anomaly(ies) were detected, including {critical_high} of critical/high severity."
            else:
                detail = f"{total} minor to medium anomaly(ies) were detected."

        return f"{opening} {detail}"

    def _generate_executive_summary(self, composite: float, tier: str, all_anomalies: list[dict]) -> str:
        """Professional banking-oriented concise summary detailing findings, impacts, and recommendations."""
        if not all_anomalies:
            return "This document has undergone multi-dimensional fraud checks and shows no signs of editing, formatting, or mathematical manipulation. All parsed details match verified credentials, and the file metadata indicates a standard scanner output. Automated approval is recommended."

        anom_descs = []
        for a in all_anomalies[:3]:
            issue = a.get("issue", "Inconsistency")
            desc = a.get("description", "")
            # Clean up desc if too long
            if len(desc) > 80:
                desc = desc[:80] + "..."
            anom_descs.append(f"{issue} ({desc})")

        anom_list_str = "; ".join(anom_descs)

        if tier == "high_risk":
            return (
                f"Critical risk indicators were detected during forensic analysis: {anom_list_str}. "
                f"These structural, mathematical, or visual inconsistencies present a high probability of document splicing or character editing. "
                f"Approving this document exposes the bank to credit risk or identity impersonation. Immediate manual rejection or professional underwriting escalation is recommended."
            )
        elif tier == "review":
            return (
                f"Forensic validation flagged moderate anomalies: {anom_list_str}. "
                f"While the layout appears largely intact, the presence of these date, bank, or formatting conflicts "
                f"requires secondary verification. The underwriting investigator should request original source documents "
                f"or cross-verify the coordinates on the official branch portal before submitting a final verdict."
            )
        elif tier == "low_risk":
            return (
                f"Minor visual or metadata issues were noted ({anom_list_str}). "
                f"Core financial data, transaction histories, and identification credentials align correctly. "
                f"The document is safe to process under standard underwriting guidelines."
            )
            
        return "Comprehensive analysis verifies the document's authenticity. No risk indicators were detected. Automatic approval recommended."

    def _risk_in_words(self, composite: float, tier: str, all_anomalies: list[dict]) -> str:
        mapping = {
            "verified": "Verified - Clean Document",
            "low_risk": "Low Risk - Safe to Process",
            "review": "Medium Risk - Manual Review Advised",
            "high_risk": "Critical Risk - Forgery Indicators Detected",
        }
        return mapping.get(tier, "Manual Review Advised")

    # ------------------------------------------------------------------ #
    #  Recommended actions
    # ------------------------------------------------------------------ #
    def _recommended_actions(self, composite: float, tier: str, risk_score: dict, all_anomalies: list[dict]) -> list[str]:
        actions: list[str] = []
        recommendation = risk_score.get("recommendation", "MANUAL REVIEW REQUIRED")
        source_set = set(a.get("_source", "") for a in all_anomalies)

        # Analyze the new tier nomenclature
        if tier == "high_risk":
            actions.append("ESCALATE: Forward document to the fraud investigation team for immediate review.")
            actions.append("Do NOT process financial transactions linked to this application.")
        elif tier == "review":
            actions.append("Assign document to a trained underwriter for secondary verification.")
            actions.append("Request the original unedited document directly from the issuing authority.")
        elif tier in ("verified", "low_risk"):
            actions.append("Document passes enterprise intelligence checks. Proceed with standard workflow.")

        if "tampering" in source_set:
            actions.append("Heatmap strongly indicates pixel-level manipulation. Document should be rejected.")
        if "amount" in source_set or "salary_manipulation" in [a.get("type", "") for a in all_anomalies]:
            actions.append("Cross-reference stated amounts with independent bank statements or ledgers.")

        if recommendation in ("VERIFIED", "SAFE TO PROCESS"):
            actions.append("Document passes intelligence checks. Proceed with standard workflow.")

        return actions

    # ------------------------------------------------------------------ #
    #  Narrative
    # ------------------------------------------------------------------ #
    def _generate_narrative(self, composite, tier, confidence, risk_score, metadata_result, tampering_result, signature_result, amount_result, anomaly_result, all_anomalies) -> str:
        paragraphs: list[str] = []

        paragraphs.append(
            f"The document was subjected to a multi-dimensional fraud analysis comprising metadata integrity checks, "
            f"image tampering detection, signature verification, and statistical cross-document anomaly detection. "
            f"The composite risk score is {composite:.1f}/100 with an overall Analysis Confidence of {confidence:.1f}%. "
            f"This places it in the {tier.replace('_', ' ').upper()} tier. "
            f"Recommended disposition: {risk_score.get('recommendation', 'MANUAL REVIEW REQUIRED')}."
        )

        sub_scores = risk_score.get("sub_scores", {})

        # Tampering
        tamp_score = sub_scores.get("tampering", 0)
        if tamp_score > 10:
            verdict = tampering_result.get("verdict", "inconclusive")
            paragraphs.append(
                f"Image-level tampering detection scored {tamp_score:.1f}/100 with a verdict of '{verdict}'. "
                f"Heatmap analysis indicates regions of irregular compression or duplication. {tampering_result.get('summary', '')}"
            )
        else:
            paragraphs.append("No significant image tampering was detected. ELA, copy-move, and noise analyses returned values within normal bounds.")

        # Cross Document & Text Anomalies
        anom_score = sub_scores.get("anomaly", 0)
        if anom_score > 10 or anomaly_result.get("total_anomalies", 0) > 0:
            paragraphs.append(
                f"Statistical and cross-field anomaly detection identified {anomaly_result.get('total_anomalies', 0)} issue(s) "
                f"(score: {anom_score:.1f}/100). {anomaly_result.get('summary', '')}"
            )

        # Closing
        recommendation = risk_score.get("recommendation", "MANUAL REVIEW REQUIRED")
        if recommendation == "REJECT APPLICATION":
            paragraphs.append("The severity of findings strongly suggests this document is fraudulent or heavily manipulated.")
        elif recommendation == "HIGH FRAUD RISK":
            paragraphs.append("The combination of anomalies indicates high risk. A manual forensic review is heavily advised.")
        elif recommendation in ("VERIFIED", "SAFE TO PROCESS"):
            paragraphs.append("Based on the analysis, this document meets the threshold for automated approval.")
        else:
            paragraphs.append("Given the findings, this document should be routed to a trained reviewer before processing.")

        return "\n\n".join(paragraphs)

