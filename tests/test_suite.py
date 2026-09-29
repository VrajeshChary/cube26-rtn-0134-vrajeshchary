import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.models import CheckVerdict, DispositionDecision, InspectionRequest
from backend.pipeline import ReturnsInspectionPipeline
from backend.storage import store

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cube-04-returns-manager"


def test_products_list():
    response = client.get("/api/products")
    assert response.status_code == 200
    products = response.json()
    assert len(products) >= 10
    skus = [p["sku"] for p in products]
    assert "SKU-LAMP-LED" in skus
    assert "SKU-PUZZLE-500" in skus


def test_pipeline_factory_sealed_restock():
    pipeline = ReturnsInspectionPipeline()
    req = InspectionRequest(
        unit_id="UNIT-TEST-1",
        order_id="ORD-1",
        ordered_sku="SKU-LAMP-LED",
        ordered_asin="B0DUMMY357",
        organization_id="org_demo_alpha",
    )
    observed = {"observed_state": "factory_sealed", "identity_match": "yes"}
    record = pipeline.process_inspection(req, observed_labels=observed)

    assert record.outcome.decision == DispositionDecision.RESTOCK
    assert record.checks[0].verdict == CheckVerdict.PASS
    assert record.checks[1].verdict == CheckVerdict.PASS
    assert record.checks[2].detail["amazon_condition"] == "New"
    assert len(record.content_hash) == 64


def test_pipeline_missing_accessory_refurbish():
    pipeline = ReturnsInspectionPipeline()
    req = InspectionRequest(
        unit_id="UNIT-TEST-2",
        order_id="ORD-2",
        ordered_sku="SKU-LAMP-LED",
        ordered_asin="B0DUMMY357",
        organization_id="org_demo_alpha",
    )
    observed = {
        "observed_state": "opened_unused",
        "parts_missing": "usb cable",
        "identity_match": "yes",
    }
    record = pipeline.process_inspection(req, observed_labels=observed)

    assert record.outcome.decision == DispositionDecision.REFURBISH
    assert record.checks[1].verdict == CheckVerdict.FAIL
    assert "usb cable" in record.checks[1].detail["missing_parts"]


def test_pipeline_broken_unit_dispose():
    pipeline = ReturnsInspectionPipeline()
    req = InspectionRequest(
        unit_id="UNIT-TEST-3",
        order_id="ORD-3",
        ordered_sku="SKU-LAMP-LED",
        ordered_asin="B0DUMMY357",
        organization_id="org_demo_alpha",
    )
    observed = {
        "observed_state": "damaged",
        "defect_type": "cracked arm and broken socket",
        "identity_match": "yes",
    }
    record = pipeline.process_inspection(req, observed_labels=observed)

    assert record.outcome.decision == DispositionDecision.DISPOSE
    assert record.checks[2].detail["amazon_condition"] == "Unacceptable"


def test_pipeline_uncertainty_handling():
    pipeline = ReturnsInspectionPipeline()
    req = InspectionRequest(
        unit_id="UNIT-TEST-4",
        order_id="ORD-4",
        ordered_sku="SKU-PUZZLE-500",
        ordered_asin="B0DUMMY729",
        organization_id="org_demo_alpha",
    )
    observed = {"observed_state": "uncertain", "identity_match": "uncertain"}
    record = pipeline.process_inspection(req, observed_labels=observed)

    assert record.outcome.decision == DispositionDecision.PENDING_REVIEW
    assert record.status == "pending_review"
    assert "Ambiguous evidence" in record.outcome.reason


def test_tenant_isolation():
    res_alpha = client.post("/api/inspect", json={
        "unit_id": "UNIT-ALPHA-01",
        "order_id": "ORD-ALPHA",
        "ordered_sku": "SKU-LAMP-LED",
        "organization_id": "org_demo_alpha",
        "observed_state": "factory_sealed"
    })
    assert res_alpha.status_code == 200
    alpha_record_id = res_alpha.json()["record_id"]

    res_bravo = client.post("/api/inspect", json={
        "unit_id": "UNIT-BRAVO-01",
        "order_id": "ORD-BRAVO",
        "ordered_sku": "SKU-BOTTLE-750",
        "organization_id": "org_demo_bravo",
        "observed_state": "factory_sealed"
    })
    assert res_bravo.status_code == 200
    bravo_record_id = res_bravo.json()["record_id"]

    list_alpha = client.get("/api/records?org_id=org_demo_alpha").json()
    alpha_ids = [r["record_id"] for r in list_alpha]
    assert alpha_record_id in alpha_ids
    assert bravo_record_id not in alpha_ids

    cross_res = client.get(f"/api/records/{alpha_record_id}?org_id=org_demo_bravo")
    assert cross_res.status_code == 404


def test_supervisor_override():
    res = client.post("/api/inspect", json={
        "unit_id": "UNIT-OVERRIDE-01",
        "order_id": "ORD-OVR",
        "ordered_sku": "SKU-LAMP-LED",
        "organization_id": "org_demo_alpha",
        "observed_state": "damaged"
    })
    record = res.json()
    rec_id = record["record_id"]
    orig_hash = record["content_hash"]
    assert record["outcome"]["decision"] == "dispose"

    ovr_res = client.post("/api/override", json={
        "organization_id": "org_demo_alpha",
        "record_id": rec_id,
        "revised_decision": "refurbish",
        "reason": "Engineering confirmed housing replacement can restore item to Like New",
        "operator_id": "sup_morales"
    })
    assert ovr_res.status_code == 200
    updated = ovr_res.json()
    assert updated["outcome"]["decision"] == "refurbish"
    assert updated["status"] == "overridden"
    assert len(updated["overrides"]) == 1
    assert updated["overrides"][0]["original_decision"] == "dispose"
    assert updated["content_hash"] != orig_hash


def test_vision_agent_evidence_extraction_integrity():
    """Verify Vision Agent does NOT populate observations from catalog SKU or scenario."""
    from backend.agents.vision_agent import VisionAgent, VisionEvidence
    from backend.catalog import get_product_by_sku

    agent = VisionAgent()
    prod = get_product_by_sku("SKU-LAMP-LED")
    hints = {"observed_state": "opened_unused", "parts_missing": "usb cable"}

    evidence = agent.extract_evidence(
        image_base64="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        catalog_product=prod,
        context_hints=hints,
    )

    assert isinstance(evidence, VisionEvidence)
    assert evidence.detected_product != prod.title, "Vision Agent must NEVER copy catalog title into detected_product!"
    assert evidence.detected_product is None
    assert evidence.confidence <= 0.50, f"Expected low confidence for placeholder image, got {evidence.confidence}"
    assert evidence.packaging_state == "uncertain"
    assert evidence.uncertainty_notes is not None


def test_unrelated_image_rejection_puzzle():
    tiny_png_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    res = client.post("/api/inspect", json={
        "unit_id": "UNIT-DEMO-UNRELATED",
        "order_id": "ORD-UNRELATED",
        "ordered_sku": "SKU-PUZZLE-500",
        "organization_id": "org_demo_alpha",
        "observed_state": "opened_unused",
        "identity_match": "yes",
        "image_base64": tiny_png_b64,
        "image_filename": "hacksmiths_united_logo.png"
    })
    assert res.status_code == 200
    data = res.json()

    identity_check = next(c for c in data["checks"] if c["check_key"] == "identity")
    assert identity_check["verdict"] in ["FAIL", "UNCERTAIN"], f"Expected FAIL or UNCERTAIN but got {identity_check['verdict']}"
    assert identity_check["verdict"] != "PASS", "Identity must NEVER be PASS for an unrelated image or logo!"

    comp_check = next(c for c in data["checks"] if c["check_key"] == "completeness")
    assert comp_check["verdict"] != "PASS", "Completeness must NEVER be PASS without visual confirmation!"

    cond_check = next(c for c in data["checks"] if c["check_key"] == "condition")
    assert cond_check["verdict"] != "PASS"

    assert data["outcome"]["decision"] != "restock", "Unrelated image must NEVER result in restock!"
    assert data["outcome"]["decision"] == "pending_review"
    assert data["status"] == "pending_review"


def test_blank_or_blurred_image_handling():
    blank_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    res_blank = client.post("/api/inspect", json={
        "unit_id": "UNIT-BLANK-01",
        "order_id": "ORD-BLANK",
        "ordered_sku": "SKU-PUZZLE-500",
        "organization_id": "org_demo_alpha",
        "observed_state": "opened_unused",
        "identity_match": "yes",
        "image_base64": blank_b64,
        "image_filename": "blank_scan.png"
    })
    assert res_blank.status_code == 200
    data_blank = res_blank.json()

    vision_check = next(c for c in data_blank["checks"] if c["check_key"] == "vision_evidence")
    assert vision_check["confidence"] <= 0.50, f"Expected vision confidence <= 0.50, got {vision_check['confidence']}"
    assert vision_check["verdict"] == "UNCERTAIN"
    assert vision_check["detail"]["uncertainty_notes"] is not None
    assert data_blank["outcome"]["decision"] == "pending_review"
    assert data_blank["status"] == "pending_review"

    import io
    from PIL import Image, ImageFilter
    img = Image.new("RGB", (100, 100), color=(100, 100, 100))
    for x in range(0, 100, 10):
        for y in range(100):
            img.putpixel((x, y), (200, 200, 200))
    blurred = img.filter(ImageFilter.GaussianBlur(radius=12))
    buf = io.BytesIO()
    blurred.save(buf, format="PNG")
    import base64
    blur_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    res_blur = client.post("/api/inspect", json={
        "unit_id": "UNIT-BLUR-01",
        "order_id": "ORD-BLUR",
        "ordered_sku": "SKU-LAMP-LED",
        "organization_id": "org_demo_alpha",
        "observed_state": "opened_unused",
        "identity_match": "yes",
        "image_base64": blur_b64,
        "image_filename": "blurred_tray.png"
    })
    assert res_blur.status_code == 200
    data_blur = res_blur.json()

    vision_blur_check = next(c for c in data_blur["checks"] if c["check_key"] == "vision_evidence")
    assert vision_blur_check["confidence"] <= 0.50, f"Expected vision confidence <= 0.50, got {vision_blur_check['confidence']}"
    assert vision_blur_check["verdict"] == "UNCERTAIN"
    assert data_blur["outcome"]["decision"] == "pending_review"
    assert data_blur["status"] == "pending_review"


def test_setup_check_and_env_loading():
    """Confirms .env loading, Gemini Vision active state, and disabled mock fallback."""
    from backend.agents.vision_agent import check_env_loading, get_setup_status

    status = get_setup_status()
    assert status["status"] == "ready"
    assert status["gemini_vision_active"] is True
    assert status["multimodal_vision_active"] is True
    assert status["provider"] == "OpenRouter"
    assert "gemini" in status["model"].lower()
    assert status["api_key_configured"] is True
    assert status["api_key_preview"] is not None
    assert "sk-" in status["api_key_preview"]
    assert len(status["api_key_preview"]) < 25  # Masked
    assert status["env_loaded"] is True
    assert status["fake_fallback_enabled"] is False

    env_info = check_env_loading()
    assert env_info["env_loaded"] is True
    assert env_info["openrouter_key_present"] is True

    response = client.get("/api/setup")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["gemini_vision_active"] is True
    assert data["multimodal_vision_active"] is True
    assert "gemini" in data["model"].lower()
    assert data["api_key_configured"] is True
    assert data["env_loaded"] is True
    assert "disabled" in data["mock_fallback"].lower()
    assert data["fake_fallback_enabled"] is False


def test_real_sample_image_endpoint():
    """Confirms that the real warehouse return inspection image is available."""
    response = client.get("/api/sample-image")
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "real_return_desk_lamp.jpg"
    assert data["sku"] == "SKU-LAMP-LED"
    assert data["base64"].startswith("data:image/jpeg;base64,")
    assert data["size_bytes"] > 1000


def test_real_gemini_vision_inference():
    """Confirms that live inspection of a real return image uses real Gemini Vision without fallback."""
    sample_resp = client.get("/api/sample-image")
    sample_data = sample_resp.json()

    inspect_resp = client.post("/api/inspect", json={
        "unit_id": "UNIT-LIVE-REAL-01",
        "order_id": "ORD-LIVE-01",
        "ordered_sku": "SKU-LAMP-LED",
        "organization_id": "org_demo_alpha",
        "observed_state": "opened_unused",
        "identity_match": "yes",
        "image_base64": sample_data["base64"],
        "image_filename": sample_data["filename"]
    })
    assert inspect_resp.status_code == 200
    record = inspect_resp.json()

    vision_check = next(c for c in record["checks"] if c["check_key"] == "vision_evidence")
    detail = vision_check["detail"]

    assert "gemini" in detail["model_used"].lower()
    assert detail["image_analyzed"] == "real_return_desk_lamp.jpg"
    assert detail["vision_confidence"] is not None
    assert detail["vision_confidence"] >= 0.70
    assert detail["detected_evidence"] is not None
    assert len(detail["detected_evidence"].get("visible_parts", [])) > 0
    assert detail["is_gemini_inference"] is True
    assert detail["is_fallback"] is False
    assert "gemini" in detail["inference_source"].lower()


def test_corrupted_base64_handling():
    """Confirms corrupted base64 image triggers quality guard and safe uncertainty state."""
    res = client.post("/api/inspect", json={
        "unit_id": "UNIT-CORRUPT-01",
        "order_id": "ORD-CORRUPT",
        "ordered_sku": "SKU-LAMP-LED",
        "organization_id": "org_demo_alpha",
        "observed_state": "opened_unused",
        "identity_match": "yes",
        "image_base64": "data:image/png;base64,!!!totally_invalid_base64_string!!!",
        "image_filename": "corrupted_scan.png"
    })
    assert res.status_code == 200
    data = res.json()

    vision_check = next(c for c in data["checks"] if c["check_key"] == "vision_evidence")
    assert vision_check["verdict"] == "UNCERTAIN"
    assert "corrupted" in vision_check["detail"]["uncertainty_notes"].lower()
    assert data["outcome"]["decision"] == "pending_review"


def test_defect_type_payload_dispatch():
    """Confirms defect_type is respected across condition agent and disposition outcome."""
    res = client.post("/api/inspect", json={
        "unit_id": "UNIT-DEFECT-01",
        "order_id": "ORD-DEFECT",
        "ordered_sku": "SKU-LAMP-LED",
        "organization_id": "org_demo_alpha",
        "observed_state": "damaged",
        "defect_type": "cracked housing arm and shattered mount",
        "identity_match": "yes"
    })
    assert res.status_code == 200
    data = res.json()

    cond_check = next(c for c in data["checks"] if c["check_key"] == "condition")
    assert cond_check["verdict"] == "FAIL"
    assert cond_check["detail"]["amazon_condition"] == "Unacceptable"
    assert data["outcome"]["decision"] == "dispose"


def test_semantic_product_identity_matching():
    """Validates semantic product matching across category, components, brand, SKU metadata, and visual features.
    
    Verifies that:
    1. Descriptions that are not text identical but share category and components PASS (e.g. lamp example).
    2. Genuinely different items FAIL (e.g. lamp expected vs shoes detected).
    3. All 5 comparison dimensions are reported in check detail.
    """
    from backend.agents.identity_agent import IdentityAgent
    from backend.catalog import get_product_by_sku

    agent = IdentityAgent()
    lamp = get_product_by_sku("SKU-LAMP-LED")
    bottle = get_product_by_sku("SKU-BOTTLE-750")

    res_lamp_pos = agent.evaluate(
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        catalog_product=lamp,
        image_metadata={
            "has_image": True,
            "detected_product": "Black articulated desk lamp with clamp base",
            "detected_brand": "AmazonBasics",
            "visible_parts": ["lamp body", "clamp base", "usb cable"],
            "confidence": 0.95,
        }
    )
    assert res_lamp_pos.verdict == CheckVerdict.PASS
    assert res_lamp_pos.confidence >= 0.92
    assert "Semantic identity match verified" in res_lamp_pos.detail["evidence"]
    comp = res_lamp_pos.detail["comparison"]
    assert "category" in comp and comp["category"]["match"] is True
    assert "key_components" in comp and comp["key_components"]["match"] is True
    assert "brand" in comp and comp["brand"]["match"] is True
    assert "sku_metadata" in comp and comp["sku_metadata"]["match"] is True
    assert "visual_features" in comp and comp["visual_features"]["match"] is True

    res_shoes = agent.evaluate(
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        catalog_product=lamp,
        image_metadata={
            "has_image": True,
            "detected_product": "Men's athletic running shoes",
            "detected_brand": "Nike",
            "visible_parts": ["laces", "rubber sole"],
            "confidence": 0.96,
        }
    )
    assert res_shoes.verdict == CheckVerdict.FAIL
    assert "Shoes & Footwear" in res_shoes.detail["evidence"]
    assert "Genuinely different product category" in res_shoes.detail["evidence"]

    res_shirt = agent.evaluate(
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        catalog_product=lamp,
        image_metadata={
            "has_image": True,
            "detected_product": "Cotton crewneck t-shirt",
            "visible_parts": ["collar", "sleeves"],
            "confidence": 0.95,
        }
    )
    assert res_shirt.verdict == CheckVerdict.FAIL
    assert "Clothing & Apparel" in res_shirt.detail["evidence"]

    res_drill = agent.evaluate(
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        catalog_product=lamp,
        image_metadata={
            "has_image": True,
            "detected_product": "20V cordless power drill with battery pack",
            "visible_parts": ["chuck", "trigger", "battery"],
            "confidence": 0.95,
        }
    )
    assert res_drill.verdict == CheckVerdict.FAIL
    assert "Power Tools" in res_drill.detail["evidence"]

    res_phone = agent.evaluate(
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        catalog_product=lamp,
        image_metadata={
            "has_image": True,
            "detected_product": "Smartphone with glass display screen",
            "visible_parts": ["screen", "camera bump"],
            "confidence": 0.95,
        }
    )
    assert res_phone.verdict == CheckVerdict.FAIL

    res_swap = agent.evaluate(
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        catalog_product=lamp,
        image_metadata={
            "has_image": True,
            "detected_product": "Double-wall insulated sports bottle 750ml",
            "visible_parts": ["bottle body", "insulated lid"],
            "confidence": 0.95,
        }
    )
    assert res_swap.verdict == CheckVerdict.FAIL
    assert "SKU-BOTTLE-750" in res_swap.detail["evidence"] or "Insulated Stainless Steel Water Bottle" in res_swap.detail["evidence"]

    res_bottle_pos = agent.evaluate(
        ordered_sku="SKU-BOTTLE-750",
        ordered_asin=bottle.asin,
        catalog_product=bottle,
        image_metadata={
            "has_image": True,
            "detected_product": "Stainless steel sports flask with leak-proof lid",
            "visible_parts": ["flask body", "lid"],
            "confidence": 0.95,
        }
    )
    assert res_bottle_pos.verdict == CheckVerdict.PASS
    assert "Semantic identity match verified" in res_bottle_pos.detail["evidence"]


def test_disposition_reasoning_priority_product_mismatch():
    """Verify that when identity check fails (e.g. wrong item / incompatible category),
    the disposition reason prioritizes 'Product mismatch / wrong item returned' over
    completeness or condition ambiguity, while keeping checks unchanged.
    """
    from backend.agents.disposition_agent import DispositionAgent
    from backend.catalog import get_product_by_sku
    from backend.models import CheckResult, CheckVerdict, DispositionDecision

    disp_agent = DispositionAgent()
    lamp = get_product_by_sku("SKU-LAMP-LED")

    id_fail = CheckResult(
        check_key="identity",
        verdict=CheckVerdict.FAIL,
        confidence=0.96,
        detail={
            "ordered_sku": "SKU-LAMP-LED",
            "reason": "Product mismatch: Detected 'Running shoes with white rubber sole' (Shoes & Footwear) directly conflicts with expected SKU SKU-LAMP-LED (Dimmable Architect LED Desk Lamp with Clamp - Home & Office). Genuinely different product category.",
            "evidence": "Product mismatch: Detected 'Running shoes with white rubber sole' (Shoes & Footwear) directly conflicts with expected SKU SKU-LAMP-LED (Dimmable Architect LED Desk Lamp with Clamp - Home & Office). Genuinely different product category.",
        },
        model_version="test-id-v1",
        latency_ms=10,
    )

    comp_uncertain = CheckResult(
        check_key="completeness",
        verdict=CheckVerdict.UNCERTAIN,
        confidence=0.5,
        detail={"reason": "Cannot verify BOM parts on unrecognized item.", "missing_parts": []},
        model_version="test-comp-v1",
        latency_ms=10,
    )

    cond_uncertain = CheckResult(
        check_key="condition",
        verdict=CheckVerdict.UNCERTAIN,
        confidence=0.5,
        detail={"reason": "Cannot assess cosmetic condition.", "amazon_condition": "Unknown"},
        model_version="test-cond-v1",
        latency_ms=10,
    )

    outcome = disp_agent.decide(
        identity_check=id_fail,
        completeness_check=comp_uncertain,
        condition_check=cond_uncertain,
        catalog_product=lamp,
    )

    assert outcome.decision == DispositionDecision.PENDING_REVIEW
    assert outcome.reason.startswith("Product mismatch / wrong item returned:")
    assert "Shoes & Footwear" in outcome.reason
    assert "Ambiguous evidence on check(s)" not in outcome.reason

    pipeline = ReturnsInspectionPipeline()
    req = InspectionRequest(
        unit_id="UNIT-TEST-MISMATCH",
        order_id="ORD-MISMATCH",
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        organization_id="org_demo_alpha",
    )
    observed = {
        "observed_state": "uncertain",  # would trigger uncertainty on completeness/condition
        "identity_match": "no",         # operator / vision identifies wrong item
    }
    record = pipeline.process_inspection(req, observed_labels=observed)

    assert record.outcome.decision == DispositionDecision.PENDING_REVIEW
    assert "Product mismatch / wrong item returned" in record.outcome.reason
    assert "Ambiguous evidence on check(s)" not in record.outcome.reason
    assert record.checks[0].verdict == CheckVerdict.FAIL
    assert record.checks[1].check_key == "completeness"
    assert record.checks[2].check_key == "condition"


def test_damaged_lamp_disposition_priority_over_completeness_uncertainty():
    """Regression test: A physically damaged lamp with condition FAIL must route to
    the appropriate damage disposition (DISPOSE) even when completeness is UNCERTAIN,
    and the final reason must explicitly mention detected physical damage.
    """
    from backend.agents.disposition_agent import DispositionAgent
    from backend.catalog import get_product_by_sku
    from backend.models import AmazonCondition, CheckResult, CheckVerdict, DispositionDecision

    disp_agent = DispositionAgent()
    lamp = get_product_by_sku("SKU-LAMP-LED")

    id_pass = CheckResult(
        check_key="identity",
        verdict=CheckVerdict.PASS,
        confidence=0.96,
        detail={
            "ordered_sku": "SKU-LAMP-LED",
            "evidence": "Semantic identity match verified: Detected articulated desk lamp aligns with catalog SKU-LAMP-LED.",
        },
        model_version="test-id-v1",
        latency_ms=10,
    )

    cond_fail = CheckResult(
        check_key="condition",
        verdict=CheckVerdict.FAIL,
        confidence=0.96,
        detail={
            "amazon_condition": AmazonCondition.UNACCEPTABLE.value,
            "observed_state": "damaged",
            "evidence": "Visual damage observed: cracked articulated arm, bent clamp, and shattered socket. Exceeds acceptable wear threshold.",
            "official_taxonomy": "Amazon Official Condition Guidelines",
        },
        model_version="test-cond-v1",
        latency_ms=10,
    )

    comp_uncertain = CheckResult(
        check_key="completeness",
        verdict=CheckVerdict.UNCERTAIN,
        confidence=0.50,
        detail={
            "evidence": "Inner compartment occluded; cannot verify presence of USB cable or manual.",
            "missing_parts": [],
        },
        model_version="test-comp-v1",
        latency_ms=10,
    )

    outcome = disp_agent.decide(
        identity_check=id_pass,
        completeness_check=comp_uncertain,
        condition_check=cond_fail,
        catalog_product=lamp,
    )

    assert outcome.decision == DispositionDecision.DISPOSE
    assert "physical damage" in outcome.reason.lower()
    assert "Ambiguous evidence" not in outcome.reason

    pipeline = ReturnsInspectionPipeline()
    req = InspectionRequest(
        unit_id="UNIT-REGRESSION-DAMAGED-LAMP",
        order_id="ORD-DAMAGED-LAMP",
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        organization_id="org_demo_alpha",
    )
    img_meta = {
        "has_image": True,
        "detected_product": "Black articulated desk lamp with clamp base",
        "packaging_state": "damaged",
        "visible_damage": ["cracked articulated arm", "broken clamp"],
        "visible_parts": ["lamp arm", "lamp head"],
        "confidence": 0.95,
    }
    record = pipeline.process_inspection(req, image_metadata=img_meta)

    assert record.checks[0].verdict == CheckVerdict.PASS       # Identity passes
    assert record.checks[1].verdict == CheckVerdict.UNCERTAIN  # Completeness is UNCERTAIN (unconfirmed accessories)
    assert record.checks[2].verdict == CheckVerdict.FAIL       # Condition fails due to damage
    assert record.outcome.decision == DispositionDecision.DISPOSE
    assert "damage" in record.outcome.reason.lower()
    assert "Ambiguous evidence" not in record.outcome.reason


def test_packaging_state_conflict_resolution_on_damage():
    """Verify that when condition FAIL detects structural damage, packaging_state
    is automatically overridden from opened_unused / factory_sealed to 'damaged'
    in the final evidence output, while preserving original Gemini observation
    and normalized condition state.
    """
    from backend.catalog import get_product_by_sku
    from backend.models import CheckVerdict, InspectionRequest
    from backend.pipeline import ReturnsInspectionPipeline

    lamp = get_product_by_sku("SKU-LAMP-LED")
    pipeline = ReturnsInspectionPipeline()
    req = InspectionRequest(
        unit_id="UNIT-TEST-PKG-OVERRIDE",
        order_id="ORD-PKG-OVERRIDE",
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        organization_id="org_demo_alpha",
    )
    img_meta = {
        "has_image": True,
        "detected_product": "Black architect-style desk lamp with a clamp base",
        "brand": "Lumina",
        "visible_parts": ["lamp", "clamp base", "lamp head", "usb cable"],
        "visible_damage": ["broken lamp head", "broken clamp base", "shattered pieces of clamp base"],
        "packaging_state": "opened_unused",
        "confidence": 1.0,
    }
    record = pipeline.process_inspection(req, image_metadata=img_meta)

    assert record.checks[2].verdict == CheckVerdict.FAIL

    ve = record.vision_evidence
    assert ve["packaging_state"] == "damaged"

    assert ve["original_packaging_state"] == "opened_unused"
    assert ve["original_gemini_observation"]["packaging_state"] == "opened_unused"
    assert "broken lamp head" in ve["original_gemini_observation"]["visible_damage"]

    assert ve["normalized_condition_state"] == "Unacceptable"

    assert record.checks[3].detail["packaging_state"] == "damaged"
    assert record.checks[3].detail["original_packaging_state"] == "opened_unused"


def test_completeness_all_bom_components_visually_confirmed_pass():
    """Verify that when all required BOM components are visually confirmed in an image
    (such as lamp, USB cable, user guide for SKU-LAMP-LED), completeness returns PASS
    instead of UNCERTAIN, and does not assume hidden/internal parts exist.
    Only returns UNCERTAIN when a required BOM component cannot be visually verified.
    """
    from backend.agents.completeness_agent import CompletenessAgent
    from backend.catalog import get_product_by_sku
    from backend.models import CheckVerdict, DispositionDecision, InspectionRequest
    from backend.pipeline import ReturnsInspectionPipeline

    agent = CompletenessAgent()
    lamp = get_product_by_sku("SKU-LAMP-LED")

    img_meta_complete = {
        "has_image": True,
        "detected_product": "Dimmable Architect LED Desk Lamp with Clamp",
        "visible_parts": [
            "articulated desk lamp",
            "clamp base",
            "USB cable",
            "user guide",
        ],
        "packaging_state": "opened_unused",
    }
    result_complete = agent.evaluate(catalog_product=lamp, image_metadata=img_meta_complete)
    assert result_complete.verdict == CheckVerdict.PASS
    assert result_complete.confidence >= 0.95
    assert "internal" not in result_complete.detail["evidence"].lower()
    assert "Vision verified all 3 required components" in result_complete.detail["evidence"]
    assert result_complete.detail["confirmed_parts"] == ["lamp", "usb cable", "manual"]

    img_meta_missing_manual = {
        "has_image": True,
        "visible_parts": [
            "articulated desk lamp",
            "clamp base",
            "USB cable",
        ],
        "packaging_state": "opened_unused",
    }
    result_unconfirmed = agent.evaluate(catalog_product=lamp, image_metadata=img_meta_missing_manual)
    assert result_unconfirmed.verdict == CheckVerdict.UNCERTAIN
    assert "manual" in result_unconfirmed.detail["unconfirmed_parts"]
    assert "internal" not in result_unconfirmed.detail["evidence"].lower()
    assert "cannot be visually verified" in result_unconfirmed.detail["evidence"].lower()

    pipeline = ReturnsInspectionPipeline()
    req = InspectionRequest(
        unit_id="UNIT-TEST-COMPLETE-LAMP",
        order_id="ORD-COMPLETE-LAMP",
        ordered_sku="SKU-LAMP-LED",
        ordered_asin=lamp.asin,
        organization_id="org_demo_alpha",
    )
    record = pipeline.process_inspection(req, image_metadata=img_meta_complete)
    assert record.checks[0].verdict == CheckVerdict.PASS  # Identity
    assert record.checks[1].verdict == CheckVerdict.PASS  # Completeness
    assert record.checks[2].verdict == CheckVerdict.PASS  # Condition
    assert record.outcome.decision == DispositionDecision.RESTOCK









