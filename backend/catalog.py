"""Product Catalogue and Bill of Materials (BOM) definitions for Returns Manager."""

from typing import Dict, List, Optional
from pydantic import BaseModel


class ProductDefinition(BaseModel):
    sku: str
    asin: str
    title: str
    category: str
    expected_parts: List[str]
    critical_parts: List[str]
    restockable_open_box: bool
    packaging_type: str
    description: str


CATALOGUE: Dict[str, ProductDefinition] = {
    "SKU-PUZZLE-500": ProductDefinition(
        sku="SKU-PUZZLE-500",
        asin="B0DUMMY729",
        title="500-Piece Panoramic Landscape Jigsaw Puzzle",
        category="Toys & Games",
        expected_parts=["puzzle pieces", "poster"],
        critical_parts=["puzzle pieces"],
        restockable_open_box=False,
        packaging_type="sealed_box",
        description="High precision cut puzzle with full color reference guide poster."
    ),
    "SKU-LAMP-LED": ProductDefinition(
        sku="SKU-LAMP-LED",
        asin="B0DUMMY357",
        title="Dimmable Architect LED Desk Lamp with Clamp",
        category="Home & Office",
        expected_parts=["lamp", "usb cable", "manual"],
        critical_parts=["lamp"],
        restockable_open_box=True,
        packaging_type="carton_box",
        description="Adjustable swing arm LED lamp with touch controls and USB power delivery."
    ),
    "SKU-TOWEL-BLU": ProductDefinition(
        sku="SKU-TOWEL-BLU",
        asin="B0DUMMY600",
        title="Ultra-Absorbent Microfiber Beach & Gym Towel (Navy)",
        category="Sports & Outdoors",
        expected_parts=["towel"],
        critical_parts=["towel"],
        restockable_open_box=False,
        packaging_type="polybag_sealed",
        description="Quick drying compact microfiber towel with hanging loop."
    ),
    "SKU-BOTTLE-750": ProductDefinition(
        sku="SKU-BOTTLE-750",
        asin="B0DUMMY622",
        title="Insulated Stainless Steel Water Bottle 750ml",
        category="Kitchen & Dining",
        expected_parts=["bottle", "lid"],
        critical_parts=["bottle", "lid"],
        restockable_open_box=False,
        packaging_type="printed_cylinder_box",
        description="Double wall vacuum insulated sports bottle with leak proof spout."
    ),
    "SKU-SERUM-30": ProductDefinition(
        sku="SKU-SERUM-30",
        asin="B0DUMMY031",
        title="Vitamin C Glow Facial Serum 30ml",
        category="Beauty & Personal Care",
        expected_parts=["bottle", "dropper", "leaflet"],
        critical_parts=["bottle", "dropper"],
        restockable_open_box=False,
        packaging_type="tamper_evident_box",
        description="Antioxidant face serum with glass dropper applicator."
    ),
    "SKU-PROT-1KG": ProductDefinition(
        sku="SKU-PROT-1KG",
        asin="B0DUMMY357",
        title="100% Pure Whey Isolate Protein Powder 1kg Vanilla",
        category="Health & Household",
        expected_parts=["tub", "scoop"],
        critical_parts=["tub"],
        restockable_open_box=False,
        packaging_type="sealed_tub_foil",
        description="Nutritional supplement in HDPE tub with induction foil seal."
    ),
    "SKU-LEASH-6FT": ProductDefinition(
        sku="SKU-LEASH-6FT",
        asin="B0DUMMY205",
        title="Heavy-Duty Mountain Climbing Rope Dog Leash 6ft",
        category="Pet Supplies",
        expected_parts=["leash"],
        critical_parts=["leash"],
        restockable_open_box=True,
        packaging_type="card_hanger",
        description="Reflective nylon rope leash with padded handle and 360 zinc alloy clasp."
    ),
    "SKU-CANDLE-3": ProductDefinition(
        sku="SKU-CANDLE-3",
        asin="B0DUMMY964",
        title="Natural Soy Aromatherapy Candle Trio Gift Set",
        category="Home & Kitchen",
        expected_parts=["candle x3", "gift box"],
        critical_parts=["candle x3", "gift box"],
        restockable_open_box=True,
        packaging_type="luxury_gift_box",
        description="Three scented soy wax candles in amber glass jars with metal lids."
    ),
    "SKU-MUG-11": ProductDefinition(
        sku="SKU-MUG-11",
        asin="B0DUMMY351",
        title="Matte Ceramic Coffee Mug Set (11oz, Pack of 2)",
        category="Kitchen & Dining",
        expected_parts=["mug x2"],
        critical_parts=["mug x2"],
        restockable_open_box=True,
        packaging_type="foam_molded_box",
        description="Two handcrafted ceramic mugs with ergonomic handle."
    ),
    "SKU-CABLE-USBC": ProductDefinition(
        sku="SKU-CABLE-USBC",
        asin="B0DUMMY261",
        title="Braided Fast Charging USB-C to USB-C Cable (2m)",
        category="Electronics",
        expected_parts=["cable"],
        critical_parts=["cable"],
        restockable_open_box=True,
        packaging_type="polybag_sealed",
        description="60W nylon braided fast charging and data sync cable."
    ),
}


def get_product_by_sku(sku: Optional[str]) -> Optional[ProductDefinition]:
    if not sku:
        return None
    return CATALOGUE.get(sku.strip())


def get_product_by_asin(asin: Optional[str]) -> Optional[ProductDefinition]:
    if not asin:
        return None
    clean_asin = asin.strip()
    for prod in CATALOGUE.values():
        if prod.asin == clean_asin:
            return prod
    return None
