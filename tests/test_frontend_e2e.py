import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)


def test_frontend_static_files_served():
    """Verify that FastAPI serves index.html, styles.css, and app.js correctly."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "Returns Manager" in res_index.text
    assert "<title>Returns Manager · Testing Console</title>" in res_index.text

    res_css = client.get("/styles.css")
    assert res_css.status_code == 200
    assert "hero-decision-card" in res_css.text

    res_js = client.get("/app.js")
    assert res_js.status_code == 200
    assert "initApp" in res_js.text


def test_frontend_health_and_setup_endpoints():
    """Verify health and setup endpoints queried by the frontend header."""
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    health_data = res_health.json()
    assert health_data["status"] in ("healthy", "ok")
    assert "multimodal_vision" in health_data

    res_setup = client.get("/api/setup")
    assert res_setup.status_code == 200
    setup_data = res_setup.json()
    assert "status" in setup_data


def test_frontend_catalog_and_sample_image_endpoints():
    """Verify catalog list and sample image used by the frontend input form."""
    res_products = client.get("/api/products")
    assert res_products.status_code == 200
    products = res_products.json()
    assert len(products) >= 1
    skus = [p["sku"] for p in products]
    assert "SKU-LAMP-LED" in skus

    res_sample = client.get("/api/sample-image")
    assert res_sample.status_code == 200
    sample_data = res_sample.json()
    assert "base64" in sample_data
    assert len(sample_data["base64"]) > 100
    assert sample_data["sku"] == "SKU-LAMP-LED"


def test_frontend_override_and_failopen_safety():
    """Verify that corrupted data fails open safely and override reseals the record."""
    # Step 1: Corrupted payload fails open to pending_review, never restock
    corrupt_payload = {
        "unit_id": "UNIT-E2E-ERR",
        "order_id": "ORD-E2E-ERR",
        "ordered_sku": "SKU-LAMP-LED",
        "organization_id": "org_demo_alpha",
        "image_base64": "data:image/jpeg;base64,corrupt_junk",
    }
    res_corrupt = client.post("/api/inspect", json=corrupt_payload)
    assert res_corrupt.status_code == 200
    rec_corrupt = res_corrupt.json()
    assert rec_corrupt["outcome"]["decision"] == "pending_review"
    assert rec_corrupt["outcome"]["decision"] != "restock"

    # Step 2: Supervisor override updates decision and seals record
    override_payload = {
        "organization_id": "org_demo_alpha",
        "record_id": rec_corrupt["record_id"],
        "revised_decision": "dispose",
        "reason": "Supervisor confirmed corrupted package with irreparable internal contents.",
        "operator_id": "sup_quality_lead",
    }
    res_override = client.post("/api/override", json=override_payload)
    assert res_override.status_code == 200
    updated_rec = res_override.json()
    assert updated_rec["outcome"]["decision"] == "dispose"
    assert len(updated_rec.get("overrides", [])) >= 1
    assert updated_rec["overrides"][0]["operator_id"] == "sup_quality_lead"


def test_frontend_security_no_exposed_secrets():
    """Verify that full API keys and private tokens are never exposed in frontend files."""
    full_api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if full_api_key:
        res_health = client.get("/api/health")
        assert full_api_key not in str(res_health.json()), "Full API key leaked in /api/health!"

        res_sample = client.get("/api/sample-image")
        assert full_api_key not in str(res_sample.json()), "Full API key leaked in /api/sample-image!"

        for fname in ["frontend/index.html", "frontend/styles.css", "frontend/app.js"]:
            with open(fname, "r", encoding="utf-8") as f:
                content = f.read()
            assert full_api_key not in content, f"Full API key leaked in {fname}!"
            assert "sk-or-v1" not in content, f"OpenRouter key prefix leaked in {fname}!"
