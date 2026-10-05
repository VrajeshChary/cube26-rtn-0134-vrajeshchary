"""Identity Agent for Returns Inspection.

Compares returned product against ordered SKU / ASIN using Semantic Product Matching.
Evaluates 5 core dimensions:
1. Product category
2. Key components
3. Brand
4. SKU metadata
5. Visual features

Verdict strictly: PASS, FAIL, or UNCERTAIN. Never guesses.
Only FAILS when the detected object is genuinely different (e.g. lamp expected vs shoes detected).
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple
from ..catalog import CATALOGUE, ProductDefinition, get_product_by_sku
from ..models import CheckResult, CheckVerdict
from ..utils import is_non_product_media, normalize_text

SEMANTIC_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "SKU-LAMP-LED": {
        "category_names": ["home & office", "lighting", "office lighting", "home decor"],
        "category_keywords": [
            "lamp", "desk lamp", "architect lamp", "reading light", "task light",
            "table lamp", "swing arm lamp", "articulated lamp", "led lamp", "lighting",
            "luminaire", "clamp lamp", "work light", "gooseneck", "light"
        ],
        "key_components": ["lamp", "arm", "clamp", "base", "usb", "cable", "cord", "led", "shade", "socket", "head"],
        "visual_features": ["articulated", "swing arm", "adjustable", "clamp", "dimmable", "touch control", "metal", "desk", "architect", "black", "gooseneck", "flexible", "hinge"],
        "brand_affiliations": ["amazonbasics", "generic", "architect", "unbranded"],
    },
    "SKU-PUZZLE-500": {
        "category_names": ["toys & games", "games & puzzles", "puzzles"],
        "category_keywords": [
            "puzzle", "jigsaw", "jigsaw puzzle", "picture puzzle", "board game", "floor puzzle", "panoramic puzzle", "game"
        ],
        "key_components": ["puzzle pieces", "pieces", "poster", "box", "cardboard"],
        "visual_features": ["panoramic", "landscape", "500-piece", "interlocking", "cardboard", "scenic"],
        "brand_affiliations": ["generic", "unbranded", "ravensburger", "buffalo"],
    },
    "SKU-TOWEL-BLU": {
        "category_names": ["sports & outdoors", "home & bath", "textiles"],
        "category_keywords": [
            "towel", "beach towel", "gym towel", "bath towel", "microfiber towel", "sports towel", "washcloth", "cloth"
        ],
        "key_components": ["towel", "cloth", "hanging loop", "fabric"],
        "visual_features": ["microfiber", "absorbent", "navy", "blue", "woven", "folded", "quick drying"],
        "brand_affiliations": ["generic", "unbranded"],
    },
    "SKU-BOTTLE-750": {
        "category_names": ["kitchen & dining", "sports & outdoors", "drinkware"],
        "category_keywords": [
            "water bottle", "bottle", "flask", "thermos", "tumbler", "sports bottle", "insulated bottle", "canteen", "drink bottle", "drinkware"
        ],
        "key_components": ["bottle", "lid", "cap", "spout", "flask", "straw"],
        "visual_features": ["stainless steel", "insulated", "cylindrical", "double wall", "metal", "750ml", "leak proof"],
        "brand_affiliations": ["generic", "unbranded", "hydro", "klean"],
    },
    "SKU-SERUM-30": {
        "category_names": ["beauty & personal care", "skincare", "cosmetics"],
        "category_keywords": [
            "serum", "facial serum", "face serum", "dropper bottle", "face oil", "skincare", "cosmetic", "essence", "dropper"
        ],
        "key_components": ["bottle", "dropper", "pipette", "vial", "leaflet", "glass"],
        "visual_features": ["glass", "amber bottle", "dropper", "30ml", "liquid", "vitamin c", "applicator"],
        "brand_affiliations": ["generic", "unbranded"],
    },
    "SKU-PROT-1KG": {
        "category_names": ["health & household", "sports nutrition", "supplements"],
        "category_keywords": [
            "protein powder", "protein", "whey", "whey protein", "isolate", "powder", "nutritional supplement", "powder tub", "supplement"
        ],
        "key_components": ["tub", "container", "scoop", "lid", "seal", "jar"],
        "visual_features": ["tub", "hdpe", "powder", "foil seal", "vanilla", "1kg", "large container", "jar"],
        "brand_affiliations": ["generic", "unbranded", "optimum"],
    },
    "SKU-LEASH-6FT": {
        "category_names": ["pet supplies", "dog supplies", "pet accessories"],
        "category_keywords": [
            "leash", "dog leash", "pet lead", "rope leash", "lead", "dog rope", "training lead"
        ],
        "key_components": ["leash", "rope", "clasp", "handle", "snap hook", "clip"],
        "visual_features": ["mountain climbing rope", "climbing rope", "braided", "padded handle", "clasp", "reflective", "nylon", "zinc alloy"],
        "brand_affiliations": ["generic", "unbranded"],
    },
    "SKU-CANDLE-3": {
        "category_names": ["home & kitchen", "home decor", "aromatherapy"],
        "category_keywords": [
            "candle", "candles", "candle set", "scented candle", "aromatherapy candle", "soy candle", "jar candle", "wax candle"
        ],
        "key_components": ["candle", "jars", "lids", "box", "gift box", "wax", "wick"],
        "visual_features": ["amber glass", "soy wax", "gift set", "trio", "metal lid", "scented", "jars"],
        "brand_affiliations": ["generic", "unbranded"],
    },
    "SKU-MUG-11": {
        "category_names": ["kitchen & dining", "dining & tableware", "drinkware"],
        "category_keywords": [
            "mug", "mugs", "coffee mug", "coffee cup", "cup", "cups", "ceramic mug", "teacup"
        ],
        "key_components": ["mug", "cup", "handle", "ceramic"],
        "visual_features": ["ceramic", "matte", "handle", "11oz", "pack of 2", "stoneware"],
        "brand_affiliations": ["generic", "unbranded"],
    },
    "SKU-CABLE-USBC": {
        "category_names": ["electronics", "mobile accessories", "cables"],
        "category_keywords": [
            "cable", "usb cable", "usb-c cable", "type-c cable", "charging cable", "cord", "data cable", "wire", "fast charger"
        ],
        "key_components": ["cable", "cord", "connector", "usb-c", "plug"],
        "visual_features": ["braided", "nylon", "usb-c", "2m", "black", "connectors", "fast charging"],
        "brand_affiliations": ["generic", "unbranded", "anker"],
    },
}

INCOMPATIBLE_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "footwear": {
        "name": "Shoes & Footwear",
        "keywords": ["shoe", "shoes", "sneaker", "sneakers", "boot", "boots", "footwear", "sandal", "sandals", "slippers", "loafers", "heels", "cleats", "oxfords"],
    },
    "apparel": {
        "name": "Clothing & Apparel",
        "keywords": ["shirt", "t-shirt", "pants", "jeans", "jacket", "dress", "hoodie", "sweater", "shorts", "coat", "apparel", "garment", "suit", "blouse", "sock", "socks", "underwear"],
    },
    "computing": {
        "name": "Computing & Mobile Devices",
        "keywords": ["laptop", "notebook computer", "smartphone", "cell phone", "iphone", "android phone", "tablet", "ipad", "keyboard", "mouse", "monitor", "display screen", "printer"],
    },
    "power_tools": {
        "name": "Power Tools & Heavy Hardware",
        "keywords": ["power drill", "drill", "chainsaw", "circular saw", "hammer", "wrench", "screwdriver", "pliers", "lawnmower", "leaf blower"],
    },
    "audio": {
        "name": "Headphones & Audio",
        "keywords": ["headphones", "earbuds", "headset", "airpods", "speaker", "soundbar"],
    },
    "appliances": {
        "name": "Major Kitchen Appliances",
        "keywords": ["blender", "microwave", "toaster", "air fryer", "refrigerator", "food processor"],
    },
    "books": {
        "name": "Books & Printed Media",
        "keywords": ["book", "novel", "textbook", "magazine", "comic book"],
    },
    "luggage": {
        "name": "Luggage & Bags",
        "keywords": ["backpack", "suitcase", "handbag", "purse", "wallet", "briefcase", "duffel bag"],
    },
    "non_product": {
        "name": "Non-Product Media / Document / Logo",
        "keywords": ["logo", "graphic", "screenshot", "screengrab", "document", "invoice", "receipt", "shipping label", "paper", "label sheet", "blank screen", "clipart", "wallpaper"],
    },
}

_INCOMPATIBLE_PATTERNS: Dict[str, re.Pattern] = {}
for _cat_id, _cat_info in INCOMPATIBLE_CATEGORIES.items():
    _sorted_kw = sorted(_cat_info["keywords"], key=len, reverse=True)
    _INCOMPATIBLE_PATTERNS[_cat_id] = re.compile(
        r"\b(?:" + "|".join(re.escape(k) for k in _sorted_kw) + r")\b",
        re.IGNORECASE,
    )

_TAXONOMY_PATTERNS: Dict[str, Dict[str, List[Tuple[str, re.Pattern]]]] = {}
for _sku, _tax in SEMANTIC_TAXONOMY.items():
    _TAXONOMY_PATTERNS[_sku] = {
        "category_keywords": [(kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)) for kw in _tax.get("category_keywords", [])],
        "key_components": [(comp, [re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in comp.split() if len(t) > 2]) for comp in _tax.get("key_components", [])],
        "visual_features": [(feat, re.compile(r"\b" + re.escape(feat) + r"\b", re.IGNORECASE)) for feat in _tax.get("visual_features", []) if len(feat) > 3],
    }


class IdentityAgent:
    def __init__(self, model_version: str = "semantic-identity-agent-v3.0"):
        self.model_version = model_version

    def evaluate(
        self,
        ordered_sku: str,
        ordered_asin: str,
        catalog_product: Optional[ProductDefinition],
        observed_labels: Optional[Dict[str, Any]] = None,
        image_metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckResult:
        start_time = time.time()
        observed_labels = observed_labels or {}
        image_metadata = image_metadata or {}

        if not catalog_product:
            catalog_product = get_product_by_sku(ordered_sku)

        if not catalog_product:
            latency_ms = int((time.time() - start_time) * 1000)
            return CheckResult(
                check_key="identity",
                verdict=CheckVerdict.UNCERTAIN,
                confidence=0.5,
                detail={
                    "reason": f"SKU {ordered_sku} not found in verified product catalogue.",
                    "ordered_sku": ordered_sku,
                    "ordered_asin": ordered_asin,
                    "evidence": "Missing catalogue baseline.",
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        has_image = image_metadata.get("has_image", False)
        detected_prod = image_metadata.get("detected_product")
        detected_brand = image_metadata.get("detected_brand")
        visible_parts = image_metadata.get("visible_parts") or []
        image_filename = image_metadata.get("image_filename") or image_metadata.get("image_analyzed")

        vision_uncertain = bool(image_metadata.get("uncertainty_notes"))
        vision_confidence = float(image_metadata.get("confidence", 0.95))

        identity_signal = observed_labels.get("identity_match")
        observed_sku = observed_labels.get("observed_sku") or image_metadata.get("detected_sku")
        wrong_item_detected = observed_labels.get("wrong_item_detected", False) or identity_signal == "no"

        if has_image:
            if wrong_item_detected or (observed_sku and observed_sku != ordered_sku):
                latency_ms = int((time.time() - start_time) * 1000)
                return CheckResult(
                    check_key="identity",
                    verdict=CheckVerdict.FAIL,
                    confidence=0.96,
                    detail={
                        "ordered_sku": ordered_sku,
                        "ordered_asin": ordered_asin,
                        "matched_expected": False,
                        "detected_sku": observed_sku or "MISMATCHED_RETURN_ITEM",
                        "evidence": f"Returned item does not match ordered SKU {ordered_sku} ({catalog_product.title}). Swapped item detected.",
                        "comparison": {
                            "category": {"match": False, "note": "Explicit wrong item flag or swapped SKU"},
                            "key_components": {"match": False},
                            "brand": {"match": False},
                            "sku_metadata": {"match": False, "observed_sku": observed_sku},
                            "visual_features": {"match": False},
                        },
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            if not detected_prod or (vision_uncertain and vision_confidence < 0.60):
                latency_ms = int((time.time() - start_time) * 1000)
                return CheckResult(
                    check_key="identity",
                    verdict=CheckVerdict.UNCERTAIN,
                    confidence=0.52,
                    detail={
                        "ordered_sku": ordered_sku,
                        "ordered_asin": ordered_asin,
                        "matched_expected": None,
                        "evidence": image_metadata.get("uncertainty_notes") or "Vision evidence cannot verify product identity against catalogue. Image quality insufficient.",
                        "comparison": {
                            "category": {"match": None, "note": "Uncertain / unidentifiable media"},
                            "key_components": {"match": None},
                            "brand": {"match": None},
                            "sku_metadata": {"match": None},
                            "visual_features": {"match": None},
                        },
                    },
                    model_version=self.model_version,
                    latency_ms=latency_ms,
                )

            semantic_res = self._evaluate_semantic_identity(
                ordered_sku=ordered_sku,
                catalog_product=catalog_product,
                detected_prod=detected_prod,
                detected_brand=detected_brand,
                visible_parts=visible_parts,
                image_filename=image_filename,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            is_non_product = semantic_res.get("is_non_product", False)
            return CheckResult(
                check_key="identity",
                verdict=semantic_res["verdict"],
                confidence=semantic_res["confidence"],
                detail={
                    "ordered_sku": ordered_sku,
                    "ordered_asin": ordered_asin,
                    "catalog_title": catalog_product.title,
                    "detected_product": detected_prod,
                    "detected_brand": detected_brand,
                    "matched_expected": semantic_res["verdict"] == CheckVerdict.PASS,
                    "is_non_product": is_non_product,
                    "physical_product_detected": not is_non_product if is_non_product else image_metadata.get("physical_product_detected", True),
                    "evidence": semantic_res["reason"],
                    "reason": semantic_res["reason"],
                    "comparison": semantic_res["comparison"],
                },
                model_version=self.model_version,
                latency_ms=latency_ms,
            )

        if wrong_item_detected or identity_signal == "no":
            return CheckResult(
                check_key="identity",
                verdict=CheckVerdict.FAIL,
                confidence=0.96,
                detail={
                    "ordered_sku": ordered_sku,
                    "ordered_asin": ordered_asin,
                    "matched_expected": False,
                    "evidence": f"Operator confirmed item mismatch for SKU {ordered_sku}.",
                },
                model_version=self.model_version,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        if identity_signal == "yes":
            return CheckResult(
                check_key="identity",
                verdict=CheckVerdict.PASS,
                confidence=0.96,
                detail={
                    "ordered_sku": ordered_sku,
                    "ordered_asin": ordered_asin,
                    "matched_expected": True,
                    "catalog_title": catalog_product.title,
                    "evidence": f"Verified physical bench inspection match for {catalog_product.title}.",
                },
                model_version=self.model_version,
                latency_ms=int((time.time() - start_time) * 1000),
            )
        elif identity_signal == "uncertain" or observed_labels.get("unclear_evidence"):
            return CheckResult(
                check_key="identity",
                verdict=CheckVerdict.UNCERTAIN,
                confidence=0.52,
                detail={
                    "ordered_sku": ordered_sku,
                    "ordered_asin": ordered_asin,
                    "evidence": "Operator marked identity as uncertain; insufficient evidence to verify SKU.",
                },
                model_version=self.model_version,
                latency_ms=int((time.time() - start_time) * 1000),
            )

        return CheckResult(
            check_key="identity",
            verdict=CheckVerdict.UNCERTAIN,
            confidence=0.50,
            detail={
                "ordered_sku": ordered_sku,
                "ordered_asin": ordered_asin,
                "evidence": "Catalogue selection alone cannot establish identity without verified visual or physical evidence.",
            },
            model_version=self.model_version,
            latency_ms=int((time.time() - start_time) * 1000),
        )

    def _evaluate_semantic_identity(
        self,
        ordered_sku: str,
        catalog_product: ProductDefinition,
        detected_prod: str,
        detected_brand: Optional[str] = None,
        visible_parts: Optional[List[str]] = None,
        image_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Performs semantic product matching across 5 dimensions:
        1. Product category
        2. Key components
        3. Brand
        4. SKU metadata
        5. Visual features

        Only FAILS when the detected object is genuinely different (e.g. lamp expected vs shoes detected).
        """
        visible_parts = visible_parts or []
        norm_detected = normalize_text(detected_prod)
        norm_parts = [normalize_text(p) for p in visible_parts]
        norm_filename = normalize_text(image_filename or "")
        combined_text = f"{norm_detected} {' '.join(norm_parts)} {norm_filename}"

        patterns = _TAXONOMY_PATTERNS.get(ordered_sku, {})
        taxonomy = SEMANTIC_TAXONOMY.get(ordered_sku, {})

        norm_title = normalize_text(catalog_product.title)
        norm_category = normalize_text(catalog_product.category)

        for cat_id, cat_info in INCOMPATIBLE_CATEGORIES.items():
            is_expected_in_cat = any(
                kw in norm_title or kw in norm_category
                for kw in cat_info["keywords"]
            )
            if is_expected_in_cat:
                continue

            cat_pat = _INCOMPATIBLE_PATTERNS.get(cat_id)
            if cat_pat and (cat_pat.search(norm_detected) or cat_pat.search(norm_filename)):
                if cat_id == "non_product":
                    return {
                        "verdict": CheckVerdict.FAIL,
                        "confidence": 0.96,
                        "is_non_product": True,
                        "reason": "Invalid return image: non-product media detected. Manual review required.",
                        "comparison": {
                            "category": {"match": False, "expected": catalog_product.category, "detected_conflict": cat_info["name"]},
                            "key_components": {"match": False, "expected": catalog_product.expected_parts, "matched": []},
                            "brand": {"match": True, "detected": detected_brand or "Not specified"},
                            "sku_metadata": {"match": False, "ordered_sku": ordered_sku, "matched_sku_tokens": []},
                            "visual_features": {"match": False, "matched_features": []},
                        },
                    }
                return {
                    "verdict": CheckVerdict.FAIL,
                    "confidence": 0.96,
                    "reason": f"Product mismatch: Detected '{detected_prod}' ({cat_info['name']}) directly conflicts with expected SKU {ordered_sku} ({catalog_product.title} - {catalog_product.category}). Genuinely different product category.",
                    "comparison": {
                        "category": {"match": False, "expected": catalog_product.category, "detected_conflict": cat_info["name"]},
                        "key_components": {"match": False, "expected": catalog_product.expected_parts, "matched": []},
                        "brand": {"match": True, "detected": detected_brand or "Not specified"},
                        "sku_metadata": {"match": False, "ordered_sku": ordered_sku, "matched_sku_tokens": []},
                        "visual_features": {"match": False, "matched_features": []},
                    },
                }

        cat_pairs = patterns.get("category_keywords") or [
            (w, re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE))
            for w in norm_title.split()
        ]
        matched_cat_keywords = [kw for kw, pat in cat_pairs if pat.search(combined_text)]
        category_matched = len(matched_cat_keywords) > 0

        if not category_matched:
            expected_kws = taxonomy.get("category_keywords", [])
            for other_sku, other_tax in SEMANTIC_TAXONOMY.items():
                if other_sku == ordered_sku:
                    continue
                other_keywords = other_tax.get("category_keywords", [])
                other_specific = [k for k in other_keywords if k not in expected_kws and len(k) > 3]
                for ok in other_specific:
                    if re.search(r"\b" + re.escape(ok) + r"\b", norm_detected, re.IGNORECASE):
                        other_prod = get_product_by_sku(other_sku)
                        other_title = other_prod.title if other_prod else other_sku
                        return {
                            "verdict": CheckVerdict.FAIL,
                            "confidence": 0.96,
                            "reason": f"Product mismatch: Detected '{detected_prod}' matches different merchandise ({other_title} - {other_sku}), not ordered SKU {ordered_sku}.",
                            "comparison": {
                                "category": {"match": False, "expected": catalog_product.category, "detected_conflict_sku": other_sku},
                                "key_components": {"match": False, "expected": catalog_product.expected_parts, "matched": []},
                                "brand": {"match": True, "detected": detected_brand or "Not specified"},
                                "sku_metadata": {"match": False, "ordered_sku": ordered_sku},
                                "visual_features": {"match": False, "matched_features": []},
                            },
                        }

        comp_pairs = patterns.get("key_components") or [
            (p, [re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in normalize_text(p).split() if len(t) > 2])
            for p in catalog_product.expected_parts
        ]
        matched_components = []
        for comp_name, term_pats in comp_pairs:
            if any(tp.search(combined_text) for tp in term_pats):
                matched_components.append(comp_name)
        matched_components = list(dict.fromkeys(matched_components))
        components_matched = len(matched_components) > 0

        brand_matched = True
        brand_note = "Aligned / Neutral"
        if detected_brand:
            norm_brand = normalize_text(detected_brand)
            if "competitor" in norm_brand:
                brand_matched = False
                brand_note = "Conflicting competitor brand"
            else:
                brand_note = f"Verified brand: {detected_brand}"

        sku_tokens = [tok.lower() for tok in ordered_sku.split("-") if len(tok) > 2 and tok.lower() != "sku"]
        matched_sku_tokens = [tok for tok in sku_tokens if re.search(r"\b" + re.escape(tok) + r"\b", combined_text, re.IGNORECASE)]
        sku_metadata_matched = len(matched_sku_tokens) > 0 or category_matched

        feat_pairs = patterns.get("visual_features") or []
        matched_features = [feat for feat, pat in feat_pairs if pat.search(combined_text)]
        matched_features = list(dict.fromkeys(matched_features))
        features_matched = len(matched_features) > 0

        comparison_dict = {
            "category": {
                "match": category_matched,
                "expected": catalog_product.category,
                "matched_keywords": matched_cat_keywords,
            },
            "key_components": {
                "match": components_matched,
                "expected": catalog_product.expected_parts,
                "matched": matched_components,
            },
            "brand": {
                "match": brand_matched,
                "detected": detected_brand or "Not specified",
                "note": brand_note,
            },
            "sku_metadata": {
                "match": sku_metadata_matched,
                "ordered_sku": ordered_sku,
                "matched_sku_tokens": matched_sku_tokens,
            },
            "visual_features": {
                "match": features_matched,
                "matched_features": matched_features,
            },
        }

        if category_matched and (components_matched or features_matched) and brand_matched:
            conf = 0.96
            evidence_str = (
                f"Semantic identity match verified: Detected '{detected_prod}' aligns with catalog "
                f"{catalog_product.title} (Category: {catalog_product.category}, "
                f"Components: {', '.join(matched_components[:3]) if matched_components else 'Core Unit'}, "
                f"Features: {', '.join(matched_features[:3]) if matched_features else 'Standard'})."
            )
            return {
                "verdict": CheckVerdict.PASS,
                "confidence": conf,
                "reason": evidence_str,
                "comparison": comparison_dict,
            }

        if category_matched and brand_matched:
            conf = 0.92
            evidence_str = (
                f"Semantic identity match verified: Detected '{detected_prod}' matches product category "
                f"'{catalog_product.category}' for {catalog_product.title}."
            )
            return {
                "verdict": CheckVerdict.PASS,
                "confidence": conf,
                "reason": evidence_str,
                "comparison": comparison_dict,
            }

        return {
            "verdict": CheckVerdict.FAIL,
            "confidence": 0.95,
            "reason": (
                f"Product mismatch: Detected '{detected_prod}' does not match expected {catalog_product.title} "
                f"({catalog_product.category}). Genuinely different product."
            ),
            "comparison": comparison_dict,
        }
