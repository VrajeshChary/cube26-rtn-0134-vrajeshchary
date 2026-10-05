"""Shared utility functions, normalization, and domain constants for Returns Manager."""

import re
from typing import Optional, Set

NON_PRODUCT_TERMS = [
    "logo", "screenshot", "document", "graphic", "invoice",
    "unrelated media", "non-product image", "non-product", "non product",
    "screengrab", "receipt", "shipping label", "paper", "label sheet",
    "blank screen", "clipart", "wallpaper", "illustration"
]

NON_PRODUCT_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in sorted(NON_PRODUCT_TERMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

DAMAGE_KEYWORDS = [
    "crack", "broken", "shattered", "frayed", "torn", "rip", "bent", "leak", "dent",
    "structural damage", "breakage", "damage observed", "damage detected"
]


def normalize_text(text: Optional[str]) -> str:
    """Cleans and standardizes text for semantic token and phrase matching."""
    return re.sub(r"[^a-z0-9\s-]", " ", (text or "").lower()).strip()


def is_non_product_media(text: Optional[str]) -> bool:
    """Returns True if the given text or filename indicates non-product media (logo, document, etc.)."""
    if not text:
        return False
    norm = normalize_text(text)
    return bool(NON_PRODUCT_PATTERN.search(norm))


def contains_damage_terms(text: Optional[str]) -> bool:
    """Returns True if the given text contains any structural physical damage indicator."""
    if not text:
        return False
    norm = (text or "").lower()
    return any(term in norm for term in DAMAGE_KEYWORDS)
