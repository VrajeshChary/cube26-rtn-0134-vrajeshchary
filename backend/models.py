import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CheckVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"


class AmazonCondition(str, Enum):
    NEW = "New"
    USED_LIKE_NEW = "Used - Like New"
    USED_VERY_GOOD = "Used - Very Good"
    USED_GOOD = "Used - Good"
    USED_ACCEPTABLE = "Used - Acceptable"
    UNACCEPTABLE = "Unacceptable"
    UNCERTAIN = "UNCERTAIN"


class DispositionDecision(str, Enum):
    RESTOCK = "restock"
    REFURBISH = "refurbish"
    LIQUIDATE = "liquidate"
    DISPOSE = "dispose"
    PENDING_REVIEW = "pending_review"


class CheckResult(BaseModel):
    check_key: str = Field(..., description="Unique check identifier, e.g. identity, completeness, condition")
    verdict: CheckVerdict = Field(..., description="PASS, FAIL, or UNCERTAIN")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    detail: Dict[str, Any] = Field(default_factory=dict, description="Supporting evidence, detections, reasoning")
    model_version: str = Field(default="cube-rtn-agent-v1.0", description="Model or heuristic engine version")
    latency_ms: int = Field(default=0, description="Latency of this check in milliseconds")


class Outcome(BaseModel):
    decision: DispositionDecision = Field(..., description="restock, refurbish, liquidate, dispose, pending_review")
    reason: str = Field(..., description="Primary justification and rule trigger for the disposition")
    decided_by: str = Field(default="agent:cube-04-returns-manager", description="Entity that made the decision")
    decided_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp")


class OverrideRecord(BaseModel):
    original_decision: str
    revised_decision: str
    reason: str
    operator_id: str
    overridden_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ReturnInspectionSubject(BaseModel):
    unit_id: str
    order_id: str
    sku: str
    asin: str
    product_name: Optional[str] = None
    category: Optional[str] = None


class InspectionRequest(BaseModel):
    unit_id: str
    order_id: str
    ordered_sku: str
    ordered_asin: str
    organization_id: str = "org_demo_alpha"
    client_id: str = "client_warehouse_central"
    operator_id: Optional[str] = None
    observed_notes: Optional[str] = None
    image_data: Optional[str] = None
    image_base64: Optional[str] = None
    image_filename: Optional[str] = None


class EvidenceRecord(BaseModel):
    record_id: str
    schema_version: str = "2.0.0"
    organization_id: str
    client_id: str
    agent: str = "cube-04-returns-manager"
    subject: ReturnInspectionSubject
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    operator_label: Dict[str, Any] = Field(default_factory=dict)
    images: List[str] = Field(default_factory=list)
    checks: List[CheckResult] = Field(default_factory=list)
    outcome: Outcome
    overrides: List[OverrideRecord] = Field(default_factory=list)
    status: str = Field(default="completed", description="completed, pending_review, failed_open")
    content_hash: str = ""
    vision_evidence: Optional[Dict[str, Any]] = None
    decision_reasoning: Optional[List[str]] = None

    def calculate_hash(self) -> str:
        """Computes deterministic SHA-256 hash of immutable evidence payload."""
        data_to_hash = {
            "record_id": self.record_id,
            "schema_version": self.schema_version,
            "organization_id": self.organization_id,
            "client_id": self.client_id,
            "agent": self.agent,
            "subject": self.subject.model_dump(),
            "captured_at": self.captured_at,
            "operator_label": self.operator_label,
            "images": self.images,
            "checks": [c.model_dump() for c in self.checks],
            "outcome": self.outcome.model_dump(),
            "overrides": [o.model_dump() for o in self.overrides],
            "status": self.status,
        }
        canonical_json = json.dumps(data_to_hash, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
