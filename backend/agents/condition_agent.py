"""Condition Agent for Returns Inspection.

Classifies returned product condition strictly using the official Amazon Condition Taxonomy:
- New
- Used - Like New
- Used - Very Good
- Used - Good
- Used - Acceptable
- Unacceptable
- UNCERTAIN (when evidence is unclear, obscured, or ambiguous)

Decision Priority:
1. Vision Agent evidence (HIGHEST)
2. Explicit operator evidence (Headless Bench Evaluation)
3. Catalogue data (Baseline reference only)

Rules:
- Never trusts observed_state dropdown alone when an image is present.
- Requires affirmative visual evidence for damage and packaging state.
- Otherwise returns UNCERTAIN. Never invents custom condition labels.
"""

import time
from typing import Any, Dict, Optional
from ..catalog import ProductDefinition
from ..models import AmazonCondition, CheckResult, CheckVerdict
from ..utils import contains_damage_terms


class ConditionAgent:
    def __init__(self, model_version: str = "condition-agent-v2.0"):
        self.model_version = model_version

    def evaluate(
        self,
        catalog_product: Optional[ProductDefinition],
        observed_labels: Optional[Dict[str, Any]] = None,
        image_metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckResult:
        start_time = time.time()
        observed_labels = observed_labels or {}
        image_metadata = image_metadata or {}

        has_image = image_metadata.get("has_image", False)
        vision_pkg_state = (image_metadata.get("packaging_state") or "").lower()
        vision_damage = image_metadata.get("visible_damage", [])
        vision_uncertain = bool(image_metadata.get("uncertainty_notes"))

        operator_state = (observed_labels.get("observed_state") or "").lower()
        operator_defect = (observed_labels.get("defect_type") or "").lower()

        def is_consumable_violation(defect_str: str) -> bool:
            if catalog_product and not catalog_product.restockable_open_box:
                if catalog_product.category in ["Beauty & Personal Care", "Health & Household"]:
                    return any(w in defect_str.lower() for w in ["tamper", "foil", "seal", "opened"])
            return False

        if has_image:
            if vision_uncertain or vision_pkg_state == "uncertain" or not vision_pkg_state:
                latency_ms = int((time.time() - start_time) * 1000)
                return CheckResult(
                    check_key="condition",
                    verdict=CheckVerdict.UNCERTAIN,
                    confidence=0.50,
                    detail={
                        "amazon_condition": AmazonCondition.UNCERTAIN.value,
                        "observed_state": vision_pkg_state or "uncertain",
                        "evidence": image_metadata.get("uncertainty_notes") or "Vision evidence cannot conclusively grade condition without manual secondary inspection. Never trusting dropdown alone.",
                        "official_taxonomy": "Amazon Official Condition Guidelines",
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            damage_str = ", ".join(vision_damage).lower()
            if (
                contains_damage_terms(damage_str)
                or "mismatch" in damage_str
                or vision_pkg_state in ["damaged", "empty_box"]
                or is_consumable_violation(damage_str)
            ):
                latency_ms = int((time.time() - start_time) * 1000)
                return CheckResult(
                    check_key="condition",
                    verdict=CheckVerdict.FAIL,
                    confidence=0.96,
                    detail={
                        "amazon_condition": AmazonCondition.UNACCEPTABLE.value,
                        "observed_state": vision_pkg_state,
                        "evidence": f"Visual damage observed: {damage_str or vision_pkg_state}. Exceeds acceptable cosmetic wear threshold.",
                        "official_taxonomy": "Amazon Official Condition Guidelines",
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            if vision_pkg_state == "factory_sealed":
                latency_ms = int((time.time() - start_time) * 1000)
                return CheckResult(
                    check_key="condition",
                    verdict=CheckVerdict.PASS,
                    confidence=0.99,
                    detail={
                        "amazon_condition": AmazonCondition.NEW.value,
                        "observed_state": "factory_sealed",
                        "evidence": "Visual confirmation of intact factory seal; pristine manufacturer packaging.",
                        "official_taxonomy": "Amazon Official Condition Guidelines",
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            if vision_pkg_state == "opened_unused":
                latency_ms = int((time.time() - start_time) * 1000)
                return CheckResult(
                    check_key="condition",
                    verdict=CheckVerdict.PASS,
                    confidence=0.94,
                    detail={
                        "amazon_condition": AmazonCondition.USED_LIKE_NEW.value,
                        "observed_state": "opened_unused",
                        "evidence": "Visual confirmation of open packaging with zero cosmetic blemishes on product.",
                        "official_taxonomy": "Amazon Official Condition Guidelines",
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            if vision_pkg_state == "signs_of_use":
                latency_ms = int((time.time() - start_time) * 1000)
                return CheckResult(
                    check_key="condition",
                    verdict=CheckVerdict.PASS,
                    confidence=0.89,
                    detail={
                        "amazon_condition": AmazonCondition.USED_GOOD.value,
                        "observed_state": "signs_of_use",
                        "evidence": "Visual confirmation of moderate cosmetic wear consistent with normal use.",
                        "official_taxonomy": "Amazon Official Condition Guidelines",
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            latency_ms = int((time.time() - start_time) * 1000)
            return CheckResult(
                check_key="condition",
                verdict=CheckVerdict.UNCERTAIN,
                confidence=0.52,
                detail={
                    "amazon_condition": AmazonCondition.UNCERTAIN.value,
                    "observed_state": vision_pkg_state,
                    "evidence": "Vision evidence could not grade condition with high confidence.",
                    "official_taxonomy": "Amazon Official Condition Guidelines",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        unclear_operator = observed_labels.get("unclear_evidence", False) or operator_state == "uncertain"
        if unclear_operator:
            latency_ms = int((time.time() - start_time) * 1000)
            return CheckResult(
                check_key="condition",
                verdict=CheckVerdict.UNCERTAIN,
                confidence=0.50,
                detail={
                    "amazon_condition": AmazonCondition.UNCERTAIN.value,
                    "observed_state": "uncertain",
                    "evidence": "Operator marked condition as uncertain; lighting or angle prevents grading.",
                    "official_taxonomy": "Amazon Official Condition Guidelines",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        if (
            contains_damage_terms(operator_defect)
            or operator_state in ["damaged", "empty_box"]
            or is_consumable_violation(operator_defect)
        ):
            latency_ms = int((time.time() - start_time) * 1000)
            return CheckResult(
                check_key="condition",
                verdict=CheckVerdict.FAIL,
                confidence=0.96,
                detail={
                    "amazon_condition": AmazonCondition.UNACCEPTABLE.value,
                    "observed_state": operator_state,
                    "evidence": f"Damage observed in inspection ({operator_defect or operator_state}). Exceeds acceptable wear threshold.",
                    "official_taxonomy": "Amazon Official Condition Guidelines",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        if operator_state == "factory_sealed":
            latency_ms = int((time.time() - start_time) * 1000)
            return CheckResult(
                check_key="condition",
                verdict=CheckVerdict.PASS,
                confidence=0.99,
                detail={
                    "amazon_condition": AmazonCondition.NEW.value,
                    "observed_state": "factory_sealed",
                    "evidence": "Operator confirmed factory seal intact; pristine manufacturer packaging.",
                    "official_taxonomy": "Amazon Official Condition Guidelines",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        if operator_state == "opened_unused":
            cond = AmazonCondition.USED_VERY_GOOD if "crumpled" in operator_defect or "corner" in operator_defect else AmazonCondition.USED_LIKE_NEW
            latency_ms = int((time.time() - start_time) * 1000)
            return CheckResult(
                check_key="condition",
                verdict=CheckVerdict.PASS,
                confidence=0.93,
                detail={
                    "amazon_condition": cond.value,
                    "observed_state": "opened_unused",
                    "evidence": "Operator verified open box in pristine operational condition.",
                    "official_taxonomy": "Amazon Official Condition Guidelines",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        if operator_state == "signs_of_use":
            cond = AmazonCondition.USED_ACCEPTABLE if any(w in operator_defect for w in ["deep", "heavy", "stain"]) else AmazonCondition.USED_GOOD
            latency_ms = int((time.time() - start_time) * 1000)
            return CheckResult(
                check_key="condition",
                verdict=CheckVerdict.PASS,
                confidence=0.89,
                detail={
                    "amazon_condition": cond.value,
                    "observed_state": "signs_of_use",
                    "evidence": "Operator verified moderate cosmetic wear consistent with normal prior use.",
                    "official_taxonomy": "Amazon Official Condition Guidelines",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        latency_ms = int((time.time() - start_time) * 1000)
        return CheckResult(
            check_key="condition",
            verdict=CheckVerdict.UNCERTAIN,
            confidence=0.50,
            detail={
                "amazon_condition": AmazonCondition.UNCERTAIN.value,
                "observed_state": operator_state,
                "evidence": "Dropdown state alone cannot verify Amazon condition without affirmative physical or visual evidence.",
                "official_taxonomy": "Amazon Official Condition Guidelines",
            },
            model_version=self.model_version,
            latency_ms=latency_ms,
        )
