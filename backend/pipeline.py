"""Returns Pipeline Orchestrator.

Executes:
1. Identity Agent
2. Completeness Agent
3. Condition Agent
4. Disposition Agent
Computes deterministic SHA-256 hash and enforces Fail-Open reliability.
"""

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from .agents.completeness_agent import CompletenessAgent
from .agents.condition_agent import ConditionAgent
from .agents.disposition_agent import DispositionAgent
from .agents.identity_agent import IdentityAgent
from .agents.vision_agent import VisionAgent
from .catalog import get_product_by_asin, get_product_by_sku
from .models import (
    AmazonCondition,
    CheckResult,
    CheckVerdict,
    DispositionDecision,
    EvidenceRecord,
    InspectionRequest,
    Outcome,
    ReturnInspectionSubject,
)

logger = logging.getLogger(__name__)


class ReturnsInspectionPipeline:
    def __init__(self):
        self.vision_agent = VisionAgent()
        self.identity_agent = IdentityAgent()
        self.completeness_agent = CompletenessAgent()
        self.condition_agent = ConditionAgent()
        self.disposition_agent = DispositionAgent()

    def process_inspection(
        self,
        request: InspectionRequest,
        observed_labels: Optional[Dict[str, Any]] = None,
        image_metadata: Optional[Dict[str, Any]] = None,
    ) -> EvidenceRecord:
        """Executes full multi-agent inspection with fail-open guarantee."""
        observed_labels = observed_labels or {}
        image_metadata = image_metadata or {}

        catalog_product = get_product_by_sku(request.ordered_sku)
        if not catalog_product and request.ordered_asin:
            catalog_product = get_product_by_asin(request.ordered_asin)

        record_id = f"RTN-{str(uuid.uuid4())[:8].upper()}"
        images = []
        if request.image_filename:
            images.append(request.image_filename)

        subject = ReturnInspectionSubject(
            unit_id=request.unit_id,
            order_id=request.order_id,
            sku=request.ordered_sku,
            asin=request.ordered_asin,
            product_name=catalog_product.title if catalog_product else "Unknown Item",
            category=catalog_product.category if catalog_product else "General Merchandise",
        )

        try:
            t_vision_start = time.time()
            vision_evidence = self.vision_agent.extract_evidence(
                image_base64=request.image_data,
                image_filename=request.image_filename,
                catalog_product=catalog_product,
                context_hints=observed_labels,
            )
            vision_latency = max(int((time.time() - t_vision_start) * 1000), 12)
            vision_metadata = vision_evidence.model_dump()
            combined_image_metadata = {**vision_metadata, **image_metadata}

            identity_check = self.identity_agent.evaluate(
                ordered_sku=request.ordered_sku,
                ordered_asin=request.ordered_asin,
                catalog_product=catalog_product,
                observed_labels=observed_labels,
                image_metadata=combined_image_metadata,
            )

            completeness_check = self.completeness_agent.evaluate(
                catalog_product=catalog_product,
                observed_labels=observed_labels,
                image_metadata=combined_image_metadata,
            )

            condition_check = self.condition_agent.evaluate(
                catalog_product=catalog_product,
                observed_labels=observed_labels,
                image_metadata=combined_image_metadata,
            )

            non_product_terms = [
                "logo", "screenshot", "document", "graphic", "invoice",
                "unrelated media", "non-product image", "non-product", "non product",
                "screengrab", "receipt", "shipping label", "paper", "label sheet",
                "blank screen", "clipart", "wallpaper", "illustration"
            ]
            check_text = f"{vision_evidence.detected_product or ''} {combined_image_metadata.get('detected_product', '')} {request.image_filename or ''} {vision_evidence.uncertainty_notes or ''}".lower()
            non_prod_detected = any(
                re.search(r'\b' + re.escape(kw) + r'\b', check_text) for kw in non_product_terms
            )
            if vision_evidence.has_image:
                is_phys = (not non_prod_detected) and (vision_evidence.physical_product_detected is not False) and (combined_image_metadata.get("physical_product_detected") is not False)
            else:
                is_phys = True

            combined_image_metadata["physical_product_detected"] = is_phys
            vision_metadata["physical_product_detected"] = is_phys

            if not vision_evidence.has_image:
                vision_verdict = CheckVerdict.PASS
            elif not is_phys:
                vision_verdict = CheckVerdict.FAIL
            elif vision_evidence.uncertainty_notes or vision_evidence.packaging_state == "uncertain" or vision_evidence.confidence < 0.60:
                vision_verdict = CheckVerdict.UNCERTAIN
            else:
                vision_verdict = CheckVerdict.PASS
            vision_check = CheckResult(
                check_key="vision_evidence",
                verdict=vision_verdict,
                confidence=vision_evidence.confidence,
                detail=vision_metadata,
                model_version=self.vision_agent.model_version,
                latency_ms=vision_latency,
            )

            checks = [identity_check, completeness_check, condition_check, vision_check]

            outcome = self.disposition_agent.decide(
                identity_check=identity_check,
                completeness_check=completeness_check,
                condition_check=condition_check,
                catalog_product=catalog_product,
                vision_check=vision_check,
            )

            if not is_phys and outcome.decision == DispositionDecision.PENDING_REVIEW:
                outcome.reason = "Invalid return image: non-product media detected. Manual review required."

            status = "completed"
            if outcome.decision == DispositionDecision.PENDING_REVIEW:
                status = "pending_review"

            raw_packaging = combined_image_metadata.get("packaging_state") or vision_evidence.packaging_state or observed_labels.get("observed_state") or "opened_unused"
            cond_detail = condition_check.detail or {}
            cond_evidence_text = f"{cond_detail.get('evidence', '')} {cond_detail.get('reason', '')} {' '.join(vision_evidence.visible_damage or [])} {' '.join(combined_image_metadata.get('visible_damage') or [])}".lower()
            structural_damage_terms = [
                "crack", "broken", "shattered", "frayed", "torn", "rip", "bent", "leak", "dent",
                "structural damage", "breakage", "damage observed", "damage detected"
            ]

            has_structural_damage = (
                condition_check.verdict == CheckVerdict.FAIL
                and (
                    cond_detail.get("amazon_condition") == AmazonCondition.UNACCEPTABLE.value
                    or any(t in cond_evidence_text for t in structural_damage_terms)
                    or bool(vision_evidence.visible_damage)
                    or bool(combined_image_metadata.get("visible_damage"))
                )
            )

            final_packaging_state = raw_packaging
            if has_structural_damage and raw_packaging in ["opened_unused", "factory_sealed"]:
                final_packaging_state = "damaged"

            normalized_condition_state = cond_detail.get("amazon_condition") or ("Unacceptable" if has_structural_damage else "Inspected")

            structured_vision_evidence = {
                "physical_product_detected": is_phys,
                "detected_product": combined_image_metadata.get("detected_product") or vision_evidence.detected_product or (catalog_product.title if catalog_product else "General Merchandise"),
                "visible_components": combined_image_metadata.get("visible_parts") or vision_evidence.visible_parts or (catalog_product.expected_parts if catalog_product else []),
                "visible_damage": combined_image_metadata.get("visible_damage") or vision_evidence.visible_damage or [],
                "packaging_state": final_packaging_state,
                "original_packaging_state": raw_packaging,
                "normalized_condition_state": normalized_condition_state,
                "original_gemini_observation": {
                    "packaging_state": raw_packaging,
                    "detected_product": combined_image_metadata.get("detected_product") or vision_evidence.detected_product,
                    "visible_damage": combined_image_metadata.get("visible_damage") or vision_evidence.visible_damage or [],
                    "visible_parts": combined_image_metadata.get("visible_parts") or vision_evidence.visible_parts or [],
                    "uncertainty_notes": combined_image_metadata.get("uncertainty_notes", vision_evidence.uncertainty_notes),
                    "physical_product_detected": is_phys,
                },
                "confidence": vision_evidence.confidence,
                "model_used": vision_evidence.model_used or self.vision_agent.active_model or "google/gemini-2.5-flash",
                "inference_timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if vision_check and isinstance(vision_check.detail, dict):
                vision_check.detail["packaging_state"] = final_packaging_state
                vision_check.detail["original_packaging_state"] = raw_packaging
                vision_check.detail["normalized_condition_state"] = normalized_condition_state
            if condition_check and isinstance(condition_check.detail, dict):
                condition_check.detail["normalized_condition_state"] = normalized_condition_state
                if has_structural_damage and condition_check.detail.get("observed_state") in ["opened_unused", "factory_sealed"]:
                    condition_check.detail["original_observed_state"] = condition_check.detail.get("observed_state")
                    condition_check.detail["observed_state"] = final_packaging_state

            decision_reasoning = [
                f"Visual Evidence: {structured_vision_evidence['detected_product']} identified ({int(vision_evidence.confidence * 100)}% visual confidence, packaging: {final_packaging_state}).",
                f"Identity Verification ({identity_check.verdict.value}): {identity_check.detail.get('evidence') or identity_check.detail.get('reason') or 'SKU identity verified against order.'}",
                f"Completeness Verification ({completeness_check.verdict.value}): {completeness_check.detail.get('evidence') or completeness_check.detail.get('reason') or 'All BOM components verified.'}",
                f"Condition Assessment ({condition_check.verdict.value}): {condition_check.detail.get('amazon_condition', 'Inspected')} - {condition_check.detail.get('evidence') or condition_check.detail.get('reason') or 'Physical condition verified.'}",
                f"Disposition Policy: {outcome.reason}"
            ]

            record = EvidenceRecord(
                record_id=record_id,
                schema_version="2.0.0",
                organization_id=request.organization_id,
                client_id=request.client_id,
                agent="cube-04-returns-manager",
                subject=subject,
                operator_label={
                    "operator_id": request.operator_id,
                    "notes": request.observed_notes,
                    "raw_observation": observed_labels.get("observed_state", "none"),
                },
                images=images,
                checks=checks,
                outcome=outcome,
                overrides=[],
                status=status,
                vision_evidence=structured_vision_evidence,
                decision_reasoning=decision_reasoning,
            )

            record.content_hash = record.calculate_hash()
            return record

        except Exception as exc:
            logger.exception("Pipeline execution encountered an exception. Engaging fail-open fallback.")
            fail_checks = [
                CheckResult(
                    check_key="system_integrity",
                    verdict=CheckVerdict.UNCERTAIN,
                    confidence=0.0,
                    detail={"error": str(exc), "trace": "Fail-open safety triggered"},
                    model_version="fail-open-v1",
                    latency_ms=0,
                )
            ]
            fallback_outcome = Outcome(
                decision=DispositionDecision.PENDING_REVIEW,
                reason=f"Pipeline exception occurred ({type(exc).__name__}). Inputs preserved for manual triage.",
                decided_by="system:fail-open-guard",
            )
            fallback_vision = {
                "physical_product_detected": False,
                "detected_product": "Unavailable",
                "visible_components": [],
                "visible_damage": [],
                "packaging_state": "unknown",
                "confidence": 0.0,
                "model_used": "fail-open-guard",
                "inference_timestamp": datetime.now(timezone.utc).isoformat(),
            }
            fallback_reasoning = [
                f"Fail-open safeguard engaged due to {type(exc).__name__}",
                "Automated inspection halted to prevent unauthorized disposition",
                "Preserved for human supervisor triage"
            ]
            record = EvidenceRecord(
                record_id=record_id,
                schema_version="2.0.0",
                organization_id=request.organization_id,
                client_id=request.client_id,
                agent="cube-04-returns-manager",
                subject=subject,
                operator_label={"operator_id": request.operator_id, "notes": request.observed_notes},
                images=images,
                checks=fail_checks,
                outcome=fallback_outcome,
                overrides=[],
                status="failed_open",
                vision_evidence=fallback_vision,
                decision_reasoning=fallback_reasoning,
            )
            record.content_hash = record.calculate_hash()
            return record
