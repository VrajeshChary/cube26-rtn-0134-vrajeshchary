import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

SCENARIOS = [
    {
        "id": "tc1_correct_product",
        "name": "Correct Product",
        "payload": {
            "unit_id": "UNIT-TC1-CORRECT",
            "order_id": "ORD-TC1",
            "ordered_sku": "SKU-LAMP-LED",
            "organization_id": "org_demo_alpha",
            "observed_state": "opened_unused",
            "identity_match": "yes",
            "parts_missing": "",
            "defect_type": "",
        },
        "expected_decision": "restock",
        "expected_status": "completed",
        "expected_identity": "PASS",
        "expected_completeness": "PASS",
        "expected_condition": "PASS",
    },
    {
        "id": "tc2_wrong_product",
        "name": "Wrong Product",
        "payload": {
            "unit_id": "UNIT-TC2-WRONG",
            "order_id": "ORD-TC2",
            "ordered_sku": "SKU-LAMP-LED",
            "organization_id": "org_demo_alpha",
            "observed_state": "opened_unused",
            "identity_match": "no",
            "parts_missing": "",
            "defect_type": "Wrong item returned: Portable Bluetooth Speaker",
        },
        "expected_decision": "pending_review",
        "expected_status": "pending_review",
        "expected_identity": "FAIL",
        "expected_completeness": "PASS",
        "expected_condition": "PASS",
    },
    {
        "id": "tc5_damaged_product",
        "name": "Damaged Product",
        "payload": {
            "unit_id": "UNIT-TC5-DAMAGED",
            "order_id": "ORD-TC5",
            "ordered_sku": "SKU-LAMP-LED",
            "organization_id": "org_demo_alpha",
            "observed_state": "damaged",
            "identity_match": "yes",
            "parts_missing": "",
            "defect_type": "Fractured arm and cracked lamp head",
        },
        "expected_decision": "dispose",
        "expected_status": "completed",
        "expected_identity": "PASS",
        "expected_completeness": "PASS",
        "expected_condition": "FAIL",
    },
    {
        "id": "tc6_missing_component",
        "name": "Missing Component",
        "payload": {
            "unit_id": "UNIT-TC6-MISSING",
            "order_id": "ORD-TC6",
            "ordered_sku": "SKU-LAMP-LED",
            "organization_id": "org_demo_alpha",
            "observed_state": "opened_unused",
            "identity_match": "yes",
            "parts_missing": "usb cable",
            "defect_type": "Essential USB charging cable missing",
        },
        "expected_decision": "refurbish",
        "expected_status": "completed",
        "expected_identity": "PASS",
        "expected_completeness": "FAIL",
        "expected_condition": "PASS",
    },
    {
        "id": "tc4_blurry_image",
        "name": "Blurry Image",
        "payload": {
            "unit_id": "UNIT-TC4-BLUR",
            "order_id": "ORD-TC4",
            "ordered_sku": "SKU-LAMP-LED",
            "organization_id": "org_demo_alpha",
            "observed_state": "uncertain",
            "identity_match": "yes",
            "image_filename": "blurred_sample.jpg",
        },
        "expected_decision": "pending_review",
        "expected_status": "pending_review",
        "expected_identity": "UNCERTAIN",
        "expected_completeness": "UNCERTAIN",
        "expected_condition": "UNCERTAIN",
    },
    {
        "id": "test_non_product",
        "name": "Non-Product Image",
        "payload": {
            "unit_id": "UNIT-TC-NONPROD",
            "order_id": "ORD-TC-NONPROD",
            "ordered_sku": "SKU-LAMP-LED",
            "organization_id": "org_demo_alpha",
            "image_filename": "company_logo_screenshot.png",
        },
        "expected_decision": "pending_review",
        "expected_status": "pending_review",
        "expected_identity": "FAIL",
        "expected_completeness": "UNCERTAIN",
        "expected_condition": "UNCERTAIN",
    },
    {
        "id": "tc7_ambiguous_product",
        "name": "Ambiguous / Multi Product",
        "payload": {
            "unit_id": "UNIT-TC-AMBIG",
            "order_id": "ORD-TC-AMBIG",
            "ordered_sku": "SKU-LAMP-LED",
            "organization_id": "org_demo_alpha",
            "observed_state": "uncertain",
            "identity_match": "uncertain",
            "defect_type": "Ambiguous parcel with multiple conflicting items visible",
        },
        "expected_decision": "pending_review",
        "expected_status": "pending_review",
        "expected_identity": "UNCERTAIN",
        "expected_completeness": "UNCERTAIN",
        "expected_condition": "UNCERTAIN",
    },
    {
        "id": "test_api_failure",
        "name": "API Failure Safe",
        "payload": {
            "unit_id": "UNIT-TC8-FAILOPEN",
            "order_id": "ORD-TC8",
            "ordered_sku": "SKU-LAMP-LED",
            "organization_id": "org_demo_alpha",
            "image_base64": "data:image/jpeg;base64,invalid_corrupt_data",
        },
        "expected_decision": "pending_review",
        "expected_status": "pending_review",
        "expected_identity": "UNCERTAIN",
        "expected_completeness": "UNCERTAIN",
        "expected_condition": "UNCERTAIN",
    },
]


def _find_check(checks, key):
    for c in checks:
        if c.get("check_key") == key or c.get("name") == key:
            return c
    return None


@pytest.mark.parametrize("sc", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_frontend_adversarial_scenario(sc):
    res = client.post("/api/inspect", json=sc["payload"])
    assert res.status_code == 200, f"Scenario {sc['id']} failed with status {res.status_code}"
    data = res.json()

    outcome = data.get("outcome", {})
    decision = outcome.get("decision", "")
    assert decision == sc["expected_decision"], (
        f"Scenario {sc['id']} expected decision '{sc['expected_decision']}', got '{decision}'"
    )
    assert data.get("status") == sc["expected_status"]

    checks = data.get("checks", [])
    id_chk = _find_check(checks, "identity")
    comp_chk = _find_check(checks, "completeness")
    cond_chk = _find_check(checks, "condition")

    assert id_chk is not None, f"Missing identity check for {sc['id']}"
    assert id_chk["verdict"] == sc["expected_identity"]

    assert comp_chk is not None, f"Missing completeness check for {sc['id']}"
    assert comp_chk["verdict"] == sc["expected_completeness"]

    assert cond_chk is not None, f"Missing condition check for {sc['id']}"
    assert cond_chk["verdict"] == sc["expected_condition"]

    # Canonical safety assertion: RESTOCK can only appear when backend decision is restock
    ui_displayed_decision = decision.upper()
    if sc["expected_decision"] != "restock":
        assert ui_displayed_decision != "RESTOCK", (
            f"Adversarial scenario {sc['id']} must NEVER display RESTOCK!"
        )
