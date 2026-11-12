"""
DocuShield AI — Analysis Pydantic Schemas (v2)

Request / response models for analysis results, risk scoring,
explainability, and the dashboard summary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ── Anomaly ──────────────────────────────────────────────────────────────────
class AnomalyDetail(BaseModel):
    """A single detected anomaly within a document."""

    type: str = Field(..., description="Category of the anomaly (e.g. 'metadata_mismatch', 'pixel_tampering')")
    severity: str = Field(..., description="low | medium | high | critical")
    description: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    page: int = Field(default=1, ge=1)
    evidence: Optional[dict[str, Any]] = None


# ── Heatmap Region ───────────────────────────────────────────────────────────
class HeatmapRegion(BaseModel):
    """A bounding box for a tampering anomaly overlaid on the document."""
    
    x: int
    y: int
    width: int
    height: int
    severity: str = Field(..., description="low | medium | high | critical")
    label: str
    confidence: float = Field(..., ge=0.0, le=100.0)


# ── Risk Score ───────────────────────────────────────────────────────────────
class SubScores(BaseModel):
    """Breakdown of the composite risk score into individual analysis axes."""

    metadata: float = Field(default=0.0, ge=0.0, le=100.0)
    tampering: float = Field(default=0.0, ge=0.0, le=100.0)
    signature: float = Field(default=0.0, ge=0.0, le=100.0)
    amount: float = Field(default=0.0, ge=0.0, le=100.0)
    anomaly: float = Field(default=0.0, ge=0.0, le=100.0)


class RiskScoreResponse(BaseModel):
    """Composite risk assessment of a document."""

    composite: float = Field(..., ge=0.0, le=100.0)
    analysis_confidence: float = Field(default=90.0, ge=0.0, le=100.0, description="Overall confidence of the analysis.")
    tier: str = Field(..., description="verified | low_risk | review | high_risk")
    sub_scores: SubScores
    recommendation: str = Field(
        ...,
        description="Human-readable recommendation (e.g., MANUAL REVIEW REQUIRED)",
    )
    detected_issues: list[dict] = Field(default_factory=list, description="Array of detected issues")
    metrics: Optional[dict] = Field(default=None, description="Optional per-module metrics (ocr_confidence, metadata_reliability, fraud_detection_confidence)")


# ── Explanation ──────────────────────────────────────────────────────────────
class ExplanationFactor(BaseModel):
    """One contributing factor to the overall risk assessment."""

    factor: str
    impact: str = Field(..., description="positive | negative | neutral")
    confidence: str = Field(..., description="low | medium | high")
    evidence: str


class ExplanationResponse(BaseModel):
    """XAI output — human-readable reasoning behind the risk score."""

    summary: str = ""
    executive_summary: str = ""
    document_status: str = "UNDER REVIEW"
    risk_in_words: str = ""
    factors: list[ExplanationFactor] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    narrative: str = ""
    anomaly_count: dict = Field(default_factory=dict)


# ── Full Analysis Response ───────────────────────────────────────────────────
class TamperingAnalysis(BaseModel):
    heatmap_regions: list[HeatmapRegion] = Field(default_factory=list)
    verdict: str = "clean"
    composite_score: float = 0.0
    confidence: float = 0.0


class WorkflowInfo(BaseModel):
    status: str = Field(default="UNASSIGNED", description="UNASSIGNED | UNDER_REVIEW | ESCALATED | APPROVED | REJECTED | CLOSED")
    assigned_analyst: Optional[str] = None
    assigned_manager: Optional[str] = None
    priority: str = Field(default="LOW", description="LOW | MEDIUM | HIGH | CRITICAL")
    escalation_reason: Optional[str] = None
    escalated_by: Optional[str] = None
    waitlist_reason: Optional[str] = None
    waitlisted_by: Optional[str] = None
    waitlist_timestamp: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Complete analysis result for a single document."""

    id: str
    document_id: str
    status: str
    risk_score: RiskScoreResponse
    explanation: ExplanationResponse
    workflow: WorkflowInfo = Field(default_factory=WorkflowInfo)
    audit_logs: list[dict] = Field(default_factory=list)
    version: int = 1
    updated_at: Optional[datetime] = None
    processing_time_ms: float = 0.0
    completed_at: Optional[datetime] = None

    # Expose raw OCR and metadata results to frontend under both names
    ocr_result: dict = Field(default_factory=dict)
    ocr: dict = Field(default_factory=dict)
    metadata_analysis: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    tampering_analysis: dict = Field(default_factory=dict)
    tampering: dict = Field(default_factory=dict)
    
    # Map anomaly_flags to anomalies under both names
    anomalies: list[AnomalyDetail] = Field(default_factory=list)
    anomaly_flags: list[AnomalyDetail] = Field(default_factory=list)

    # Multi-user Case notes and audit decisions
    notes: list[dict] = Field(default_factory=list)
    decisions: list[dict] = Field(default_factory=list)


    @model_validator(mode="before")
    @classmethod
    def populate_aliases_and_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Map ocr_result <-> ocr
            if "ocr_result" in data and "ocr" not in data:
                data["ocr"] = data["ocr_result"]
            elif "ocr" in data and "ocr_result" not in data:
                data["ocr_result"] = data["ocr"]
                
            # Map metadata_analysis <-> metadata
            if "metadata_analysis" in data and "metadata" not in data:
                data["metadata"] = data["metadata_analysis"]
            elif "metadata" in data and "metadata_analysis" not in data:
                data["metadata_analysis"] = data["metadata"]
                
            # Map tampering_analysis <-> tampering
            if "tampering_analysis" in data and "tampering" not in data:
                data["tampering"] = data["tampering_analysis"]
            elif "tampering" in data and "tampering_analysis" not in data:
                data["tampering_analysis"] = data["tampering"]
                
            # Map anomaly_flags <-> anomalies
            if "anomaly_flags" in data and "anomalies" not in data:
                data["anomalies"] = data["anomaly_flags"]
            elif "anomalies" in data and "anomaly_flags" not in data:
                data["anomaly_flags"] = data["anomalies"]
        return data

    model_config = {"from_attributes": True, "populate_by_name": True, "extra": "ignore"}


class AnalysisTriggerResponse(BaseModel):
    """Returned when an analysis is kicked off asynchronously."""

    analysis_id: str
    document_id: str
    status: str = "pending"
    processing_time_ms: float = 0.0
    message: str = "Analysis has been queued"


# ── Dashboard ────────────────────────────────────────────────────────────────
class DashboardSummary(BaseModel):
    """Aggregated statistics for the operator dashboard."""

    total_scanned: int = 0
    total_flagged: int = 0
    total_blocked: int = 0
    total_approved: int = 0
    avg_processing_time_ms: float = 0.0
    fraud_rate_percent: float = 0.0
