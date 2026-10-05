"""Disposition Agent for Returns Management.

Policy-governed engine returning strictly one of:
- restock
- refurbish
- liquidate
- dispose
- pending_review

Applies strict commercial and safety guardrails across identity, completeness, and condition.
"""

from typing import Optional
from ..catalog import ProductDefinition
from ..models import AmazonCondition, CheckResult, CheckVerdict, DispositionDecision, Outcome
from ..utils import is_non_product_media


class DispositionAgent:
    def __init__(self, agent_name: str = "agent:cube-04-returns-manager"):
        self.agent_name = agent_name

    def decide(
        self,
        identity_check: CheckResult,
        completeness_check: CheckResult,
        condition_check: CheckResult,
        catalog_product: Optional[ProductDefinition],
        vision_check: Optional[CheckResult] = None,
    ) -> Outcome:
        id_detail = identity_check.detail or {}
        v_detail = vision_check.detail if vision_check else {}

        is_non_prod = False
        if id_detail.get("physical_product_detected") is False or v_detail.get("physical_product_detected") is False:
            is_non_prod = True
        elif id_detail.get("is_non_product") is True:
            is_non_prod = True
        else:
            combined_texts = " ".join([
                str(id_detail.get("detected_product") or ""),
                str(id_detail.get("reason") or ""),
                str(id_detail.get("evidence") or ""),
                str(id_detail.get("comparison", {}).get("category", {}).get("detected_conflict") or ""),
                str(v_detail.get("detected_product") or ""),
                str(v_detail.get("image_analyzed") or ""),
                str(v_detail.get("uncertainty_notes") or ""),
            ])
            is_non_prod = is_non_product_media(combined_texts)

        if is_non_prod:
            return Outcome(
                decision=DispositionDecision.PENDING_REVIEW,
                reason="Invalid return image: non-product media detected. Manual review required.",
                decided_by=self.agent_name,
            )

        if identity_check.verdict == CheckVerdict.FAIL:
            id_detail = identity_check.detail or {}
            id_evidence = (
                id_detail.get("reason")
                or id_detail.get("evidence")
                or f"Returned item does not match ordered SKU/ASIN ({catalog_product.title if catalog_product else ''})."
            )
            clean_evidence = id_evidence
            if clean_evidence.lower().startswith("product mismatch:"):
                clean_evidence = clean_evidence[len("product mismatch:"):].strip()
            elif clean_evidence.lower().startswith("product mismatch"):
                clean_evidence = clean_evidence[len("product mismatch"):].strip().lstrip(":- ")

            return Outcome(
                decision=DispositionDecision.PENDING_REVIEW,
                reason=f"Product mismatch / wrong item returned: {clean_evidence}",
                decided_by=self.agent_name,
            )

        if identity_check.verdict == CheckVerdict.UNCERTAIN:
            return Outcome(
                decision=DispositionDecision.PENDING_REVIEW,
                reason="Ambiguous evidence on check(s): [identity]. Requires human supervisor bench inspection.",
                decided_by=self.agent_name,
            )

        amazon_cond = condition_check.detail.get("amazon_condition", "")
        cond_evidence = (
            condition_check.detail.get("evidence")
            or condition_check.detail.get("reason")
            or condition_check.detail.get("observed_state")
            or "structural damage or functional failure"
        )

        if condition_check.verdict == CheckVerdict.FAIL:
            if catalog_product and not catalog_product.restockable_open_box:
                if catalog_product.category in ["Beauty & Personal Care", "Health & Household"]:
                    return Outcome(
                        decision=DispositionDecision.DISPOSE,
                        reason=f"Physical damage / seal breach in consumable category ({catalog_product.category}): {cond_evidence}. Prohibited from resale or restock under hygiene safety policy.",
                        decided_by=self.agent_name,
                    )

            if amazon_cond in [AmazonCondition.USED_VERY_GOOD.value, AmazonCondition.USED_LIKE_NEW.value]:
                return Outcome(
                    decision=DispositionDecision.REFURBISH,
                    reason=f"Physical damage detected ({cond_evidence}). Blemish is serviceable; routed to prep center for cleaning, repair, and repackaging.",
                    decided_by=self.agent_name,
                )

            return Outcome(
                decision=DispositionDecision.DISPOSE,
                reason=f"Physical damage detected: {cond_evidence}. Condition classified as Unacceptable due to structural damage, breakage, or functional failure; designated for scrap/disposal.",
                decided_by=self.agent_name,
            )

        if condition_check.verdict == CheckVerdict.UNCERTAIN:
            uncertain_checks = ["condition"]
            if completeness_check.verdict == CheckVerdict.UNCERTAIN:
                uncertain_checks.append("completeness")
            return Outcome(
                decision=DispositionDecision.PENDING_REVIEW,
                reason=f"Ambiguous evidence on check(s): [{', '.join(uncertain_checks)}]. Requires human supervisor bench inspection.",
                decided_by=self.agent_name,
            )

        if completeness_check.verdict == CheckVerdict.UNCERTAIN:
            return Outcome(
                decision=DispositionDecision.PENDING_REVIEW,
                reason="Ambiguous evidence on check(s): [completeness]. Requires human supervisor bench inspection.",
                decided_by=self.agent_name,
            )

        missing_parts = completeness_check.detail.get("missing_parts", [])
        critical_missing = completeness_check.detail.get("critical_missing", [])

        if catalog_product and not catalog_product.restockable_open_box:
            if amazon_cond in [AmazonCondition.USED_LIKE_NEW.value, AmazonCondition.USED_VERY_GOOD.value, AmazonCondition.USED_GOOD.value, AmazonCondition.USED_ACCEPTABLE.value]:
                if catalog_product.category in ["Beauty & Personal Care", "Health & Household"]:
                    return Outcome(
                        decision=DispositionDecision.DISPOSE,
                        reason=f"Open/unsealed unit in consumable category ({catalog_product.category}). Prohibited from resale or restock under hygiene safety policy.",
                        decided_by=self.agent_name,
                    )

        if critical_missing:
            return Outcome(
                decision=DispositionDecision.DISPOSE,
                reason=f"Non-replaceable critical component(s) missing: {', '.join(critical_missing)}. Cannot be restored to operational inventory.",
                decided_by=self.agent_name,
            )

        if missing_parts:
            return Outcome(
                decision=DispositionDecision.REFURBISH,
                reason=f"Minor accessory missing ({', '.join(missing_parts)}). Unit eligible for re-kitting and repacking in prep center.",
                decided_by=self.agent_name,
            )

        if amazon_cond == AmazonCondition.USED_VERY_GOOD.value:
            return Outcome(
                decision=DispositionDecision.REFURBISH,
                reason="Unit in high-grade operational order with minor packaging blemish. Eligible for cleaning, inspection, and repackaging.",
                decided_by=self.agent_name,
            )

        if amazon_cond in [AmazonCondition.USED_GOOD.value, AmazonCondition.USED_ACCEPTABLE.value]:
            return Outcome(
                decision=DispositionDecision.LIQUIDATE,
                reason=f"Item functions properly with Amazon condition '{amazon_cond}'. Routed to wholesale B2B liquidation pallet.",
                decided_by=self.agent_name,
            )

        if amazon_cond == AmazonCondition.NEW.value:
            return Outcome(
                decision=DispositionDecision.RESTOCK,
                reason="Factory sealed, brand new, 100% complete. Cleared for immediate FBA/merchant inventory restock.",
                decided_by=self.agent_name,
            )

        if amazon_cond == AmazonCondition.USED_LIKE_NEW.value:
            if catalog_product and catalog_product.restockable_open_box:
                return Outcome(
                    decision=DispositionDecision.RESTOCK,
                    reason="Open-box pristine condition with complete components. Cleared for open-box prime restock.",
                    decided_by=self.agent_name,
                )
            else:
                return Outcome(
                    decision=DispositionDecision.REFURBISH,
                    reason="Open box in pristine condition; requires inspection and re-sealing before restock.",
                    decided_by=self.agent_name,
                )

        return Outcome(
            decision=DispositionDecision.PENDING_REVIEW,
            reason="Unclassified scenario. Diverted to manual review.",
            decided_by=self.agent_name,
        )
