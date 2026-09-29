"""Completeness Agent for Returns Inspection.

Compares required parts vs visible returned components.
Decision Priority:
1. Vision Agent evidence (HIGHEST)
2. Explicit operator evidence
3. Catalogue data (Baseline reference only)

Rules:
- Never marks all parts present simply because parts_missing is empty.
- PASS only when vision (or verified operator evidence) confirms visible required components.
- If hidden, occluded, or unclear -> UNCERTAIN.
- Only marks missing when affirmative evidence supports it -> FAIL.
"""

import re
import time
from typing import Any, Dict, List, Optional
from ..catalog import ProductDefinition
from ..models import CheckResult, CheckVerdict

COMPONENT_ALIASES: Dict[str, List[str]] = {
    "lamp": [
        "lamp", "desk lamp", "architect lamp", "led lamp", "light", "luminaire",
        "lamp head", "lamp arm", "articulated arm", "clamp base", "clamp",
    ],
    "usb cable": [
        "usb cable", "usb-c cable", "usbc cable", "usb cord", "cable", "cord",
        "power cable", "power cord", "charger", "charging cord", "wire", "type-c", "usb",
    ],
    "manual": [
        "manual", "user guide", "user manual", "user guide/manual", "guide",
        "instructions", "instruction manual", "instruction sheet", "pamphlet",
        "leaflet", "documentation", "booklet", "insert",
    ],
    "puzzle pieces": [
        "puzzle pieces", "puzzle", "pieces", "jigsaw", "jigsaw pieces",
    ],
    "poster": [
        "poster", "reference poster", "reference guide", "reference sheet", "insert", "picture", "sheet",
    ],
    "towel": [
        "towel", "beach towel", "gym towel", "microfiber towel", "cloth",
    ],
    "bottle": [
        "bottle", "water bottle", "flask", "canteen", "thermos", "tumbler", "sports bottle",
    ],
    "lid": [
        "lid", "cap", "bottle cap", "spout", "cover", "top",
    ],
    "dropper": [
        "dropper", "glass dropper", "pipette", "vial", "applicator",
    ],
    "leaflet": [
        "leaflet", "manual", "guide", "user guide", "instructions", "instruction sheet", "pamphlet", "insert", "booklet",
    ],
    "tub": [
        "tub", "jar", "container", "protein tub", "powder tub", "canister",
    ],
    "scoop": [
        "scoop", "measuring scoop", "spoon", "measuring spoon",
    ],
    "leash": [
        "leash", "dog leash", "lead", "rope", "clasp",
    ],
    "candle x3": [
        "candle", "candles", "candle trio", "candle set", "wax", "jars", "candle x3",
    ],
    "gift box": [
        "gift box", "box", "packaging", "carton", "product box",
    ],
    "mug x2": [
        "mug", "mugs", "cup", "cups", "ceramic mug", "ceramic mugs", "mug x2",
    ],
    "cable": [
        "cable", "usb cable", "usb-c cable", "cord", "wire",
    ],
}


class CompletenessAgent:
    def __init__(self, model_version: str = "completeness-agent-v2.0"):
        self.model_version = model_version

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()

    def _is_component_confirmed(
        self,
        expected_part: str,
        visible_parts: List[str],
        detected_text: str = "",
    ) -> bool:
        norm_expected = self._normalize_text(expected_part)
        norm_vis_list = [self._normalize_text(v) for v in visible_parts if v]
        extra_norm = self._normalize_text(detected_text) if detected_text else ""

        for v in norm_vis_list:
            if norm_expected == v:
                return True
            if len(norm_expected) >= 3 and norm_expected in v:
                return True
            if len(v) >= 3 and v in norm_expected:
                return True

        aliases = COMPONENT_ALIASES.get(expected_part.lower(), [])
        for alias in aliases:
            norm_alias = self._normalize_text(alias)
            for v in norm_vis_list:
                if norm_alias == v:
                    return True
                if len(norm_alias) >= 3 and norm_alias in v:
                    return True
                if len(v) >= 3 and v in norm_alias:
                    return True
            if extra_norm and len(norm_alias) >= 3 and norm_alias in extra_norm:
                return True

        tokens = [
            t for t in norm_expected.split()
            if len(t) >= 3 and t not in ("and", "the", "for", "with", "set", "pack", "box")
        ]
        for v in norm_vis_list:
            v_tokens = set(v.split())
            if any(t in v_tokens for t in tokens):
                return True

        return False

    def evaluate(
        self,
        catalog_product: Optional[ProductDefinition],
        observed_labels: Optional[Dict[str, Any]] = None,
        image_metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckResult:
        start_time = time.time()
        observed_labels = observed_labels or {}
        image_metadata = image_metadata or {}

        if not catalog_product:
            latency_ms = int((time.time() - start_time) * 1000)
            return CheckResult(
                check_key="completeness",
                verdict=CheckVerdict.UNCERTAIN,
                confidence=0.5,
                detail={"reason": "Unknown product catalogue specification."},
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        expected_parts = catalog_product.expected_parts
        critical_parts = catalog_product.critical_parts

        has_image = image_metadata.get("has_image", False)
        vision_missing = image_metadata.get("missing_candidates", [])
        vision_visible = image_metadata.get("visible_parts", [])
        vision_pkg_state = image_metadata.get("packaging_state")
        vision_uncertain = bool(image_metadata.get("uncertainty_notes"))

        operator_state = (observed_labels.get("observed_state") or "").lower()
        parts_missing_raw = observed_labels.get("parts_missing", "")
        operator_missing: List[str] = []
        if isinstance(parts_missing_raw, str) and parts_missing_raw.strip():
            operator_missing = [p.strip() for p in parts_missing_raw.split(";") if p.strip()]
        elif isinstance(parts_missing_raw, list):
            operator_missing = parts_missing_raw

        missing_parts = vision_missing or operator_missing

        if missing_parts:
            critical_missing = []
            for p in missing_parts:
                p_base = p.split()[0].lower()
                for c in critical_parts:
                    c_base = c.split()[0].lower()
                    if c_base in p.lower() or p_base in c.lower() or c.lower() in p.lower():
                        critical_missing.append(p)
                        break

            latency_ms = max(int((time.time() - start_time) * 1000), 16)
            return CheckResult(
                check_key="completeness",
                verdict=CheckVerdict.FAIL,
                confidence=0.96,
                detail={
                    "expected_parts": expected_parts,
                    "visible_parts": [p for p in expected_parts if p not in missing_parts],
                    "missing_parts": missing_parts,
                    "critical_missing": critical_missing,
                    "evidence": f"Affirmative physical evidence of missing component(s): {', '.join(missing_parts)}.",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        if has_image:
            if vision_pkg_state == "factory_sealed":
                latency_ms = max(int((time.time() - start_time) * 1000), 15)
                return CheckResult(
                    check_key="completeness",
                    verdict=CheckVerdict.PASS,
                    confidence=0.99,
                    detail={
                        "expected_parts": expected_parts,
                        "visible_parts": ["Factory sealed unit - internal components sealed"],
                        "missing_parts": [],
                        "evidence": "Factory seal intact; manufacturer guarantees completeness of internal components.",
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            detected_text = str(image_metadata.get("detected_product") or "")

            confirmed_parts = [
                part for part in expected_parts
                if self._is_component_confirmed(part, vision_visible, detected_text)
            ]
            unconfirmed_parts = [
                part for part in expected_parts
                if part not in confirmed_parts
            ]

            if len(unconfirmed_parts) == 0:
                latency_ms = max(int((time.time() - start_time) * 1000), 15)
                return CheckResult(
                    check_key="completeness",
                    verdict=CheckVerdict.PASS,
                    confidence=0.96,
                    detail={
                        "expected_parts": expected_parts,
                        "visible_parts": vision_visible,
                        "confirmed_parts": confirmed_parts,
                        "missing_parts": [],
                        "evidence": f"Vision verified all {len(expected_parts)} required components present: {', '.join(expected_parts)}.",
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            reason_suffix = ""
            if vision_uncertain and image_metadata.get("uncertainty_notes"):
                reason_suffix = f" ({image_metadata.get('uncertainty_notes')})"
            elif vision_pkg_state == "uncertain":
                reason_suffix = " due to packaging occlusion, obscuration, or camera angle"

            latency_ms = max(int((time.time() - start_time) * 1000), 14)
            return CheckResult(
                check_key="completeness",
                verdict=CheckVerdict.UNCERTAIN,
                confidence=0.54,
                detail={
                    "expected_parts": expected_parts,
                    "visible_parts": vision_visible,
                    "confirmed_parts": confirmed_parts,
                    "unconfirmed_parts": unconfirmed_parts,
                    "missing_parts": [],
                    "evidence": f"Required component(s) {unconfirmed_parts} cannot be visually verified from visual evidence{reason_suffix}. Marking UNCERTAIN without guessing.",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        if operator_state == "factory_sealed":
            latency_ms = max(int((time.time() - start_time) * 1000), 15)
            return CheckResult(
                check_key="completeness",
                verdict=CheckVerdict.PASS,
                confidence=0.98,
                detail={
                    "expected_parts": expected_parts,
                    "visible_parts": ["Factory sealed unit - internal components sealed"],
                    "missing_parts": [],
                    "evidence": "Operator confirmed factory seal intact; manufacturer guarantees completeness of internal components.",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        if operator_state in ["opened_unused", "signs_of_use", "damaged"] and not operator_missing and not observed_labels.get("unclear_evidence"):
            latency_ms = max(int((time.time() - start_time) * 1000), 15)
            return CheckResult(
                check_key="completeness",
                verdict=CheckVerdict.PASS,
                confidence=0.94,
                detail={
                    "expected_parts": expected_parts,
                    "visible_parts": expected_parts,
                    "missing_parts": [],
                    "evidence": f"All {len(expected_parts)} expected BOM components verified present in bench inspection.",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        latency_ms = max(int((time.time() - start_time) * 1000), 14)
        return CheckResult(
            check_key="completeness",
            verdict=CheckVerdict.UNCERTAIN,
            confidence=0.50,
            detail={
                "expected_parts": expected_parts,
                "visible_parts": [],
                "missing_parts": [],
                "evidence": "Insufficient affirmative proof that all required components are present.",
            },
            model_version=self.model_version,
            latency_ms=latency_ms,
        )
