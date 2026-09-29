"""FastAPI Application for Cube Buildathon Returns Manager."""

import base64
import csv
import os
from pathlib import Path
import uuid
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .catalog import CATALOGUE, get_product_by_sku
from .models import EvidenceRecord, InspectionRequest
from .pipeline import ReturnsInspectionPipeline
from .storage import store

app = FastAPI(
    title="Cube 04 · Returns Inspection & Disposition Manager",
    description="Production-style Returns Inspection Agent with Evidence & Tamper-Evident Hashing.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = ReturnsInspectionPipeline()


class InspectionPayload(BaseModel):
    unit_id: Optional[str] = None
    order_id: Optional[str] = None
    ordered_sku: str
    ordered_asin: Optional[str] = None
    organization_id: str = "org_demo_alpha"
    client_id: str = "client_warehouse_central"
    operator_id: Optional[str] = None
    observed_state: Optional[str] = "opened_unused"
    parts_missing: Optional[str] = ""
    identity_match: Optional[str] = "yes"
    defect_type: Optional[str] = ""
    notes: Optional[str] = None
    image_filename: Optional[str] = None
    image_base64: Optional[str] = None


class OverridePayload(BaseModel):
    organization_id: str
    record_id: str
    revised_decision: str
    reason: str
    operator_id: Optional[str] = None


@app.get("/api/health")
def health_check():
    setup_status = pipeline.vision_agent.get_setup_status()
    return {
        "status": "healthy",
        "service": "cube-04-returns-manager",
        "stage": "Step 4 of 5 · Customer Return",
        "consumer": "Recovery Manager",
        "multimodal_vision": setup_status,
    }


@app.get("/api/setup")
def setup_check():
    """Safe setup check confirming whether Multimodal Vision inference is active."""
    return pipeline.vision_agent.get_setup_status()


@app.get("/api/sample-image")
def get_sample_image():
    """Returns the real warehouse return inspection image in base64."""
    img_path = Path(__file__).resolve().parent.parent / "data" / "real_return_desk_lamp.jpg"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found")
    data_b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
    return {
        "filename": "real_return_desk_lamp.jpg",
        "sku": "SKU-LAMP-LED",
        "mime_type": "image/jpeg",
        "base64": f"data:image/jpeg;base64,{data_b64}",
        "size_bytes": img_path.stat().st_size,
    }


@app.get("/api/sample-returns")
def list_sample_returns():
    """Returns real benchmark records from the official returns_sample.csv dataset."""
    csv_path = Path(__file__).resolve().parent.parent / "data" / "returns_sample.csv"
    if not csv_path.exists():
        return []
    records = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({
                "record_id": row.get("record_id", ""),
                "unit_id": row.get("unit_id", ""),
                "org_id": row.get("org_id", ""),
                "order_id": row.get("order_id", ""),
                "ordered_sku": row.get("ordered_sku", ""),
                "ordered_asin": row.get("ordered_asin", ""),
                "identity_match": row.get("identity_match", "yes"),
                "parts_list": row.get("parts_list", ""),
                "parts_missing": row.get("parts_missing", ""),
                "observed_state": row.get("observed_state", "opened_unused"),
                "operator_disposition": row.get("operator_disposition", ""),
                "operator_id": row.get("operator_id", ""),
                "captured_at": row.get("captured_at", "")
            })
    return records


@app.get("/api/products")
def list_products():
    """Returns available products from catalogue with BOM specifications."""
    return [
        {
            "sku": p.sku,
            "asin": p.asin,
            "title": p.title,
            "category": p.category,
            "expected_parts": p.expected_parts,
            "critical_parts": p.critical_parts,
            "restockable_open_box": p.restockable_open_box,
            "packaging_type": p.packaging_type,
            "description": p.description,
        }
        for p in CATALOGUE.values()
    ]


@app.post("/api/inspect", response_model=EvidenceRecord)
def inspect_return(payload: InspectionPayload):
    """Executes Identity, Completeness, Condition, and Disposition agents."""
    prod = get_product_by_sku(payload.ordered_sku)
    asin = payload.ordered_asin or (prod.asin if prod else "B0UNKNOWN")

    unit_id = payload.unit_id.strip() if payload.unit_id and payload.unit_id.strip() else f"UNIT-{uuid.uuid4().hex[:8].upper()}"
    order_id = payload.order_id.strip() if payload.order_id and payload.order_id.strip() else f"ORD-{uuid.uuid4().hex[:8].upper()}"
    operator_id = payload.operator_id.strip() if payload.operator_id and payload.operator_id.strip() else "station_operator"

    request = InspectionRequest(
        unit_id=unit_id,
        order_id=order_id,
        ordered_sku=payload.ordered_sku,
        ordered_asin=asin,
        organization_id=payload.organization_id,
        client_id=payload.client_id,
        operator_id=operator_id,
        observed_notes=payload.notes,
        image_data=payload.image_base64,
        image_filename=payload.image_filename,
    )

    observed_labels = {
        "observed_state": payload.observed_state,
        "parts_missing": payload.parts_missing,
        "identity_match": payload.identity_match,
        "defect_type": payload.defect_type,
        "wrong_item_detected": payload.identity_match == "no",
        "has_missing_evidence": bool(payload.parts_missing and payload.parts_missing.strip()),
        "unclear_evidence": payload.observed_state == "uncertain" or payload.identity_match == "uncertain",
    }

    record = pipeline.process_inspection(
        request=request,
        observed_labels=observed_labels,
    )

    store.save_record(record)
    return record


@app.get("/api/records")
def list_records(org_id: str = Query(..., description="Organization tenant ID")):
    """Strict tenant-isolated record listing."""
    return store.list_records(org_id=org_id)


@app.get("/api/records/{record_id}")
def get_record(record_id: str, org_id: str = Query(...)):
    """Fetch single evidence record enforcing tenant isolation."""
    record = store.get_record(org_id=org_id, record_id=record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found in current organization scope.")
    return record


@app.post("/api/override")
def override_record(payload: OverridePayload):
    """Enables human supervisors to override an agent disposition with reason code."""
    operator_id = payload.operator_id.strip() if payload.operator_id and payload.operator_id.strip() else "supervisor"
    updated = store.add_override(
        org_id=payload.organization_id,
        record_id=payload.record_id,
        revised_decision=payload.revised_decision,
        reason=payload.reason,
        operator_id=operator_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Record not found or tenant mismatch.")
    return updated


@app.get("/api/eval/run")
def trigger_evaluation():
    """Runs 50-unit evaluation suite and returns metrics."""
    from evaluation.run_eval import run_evaluation
    results = run_evaluation()
    return results


ADVERSARIAL_CASES = [
    {
        "id": "tc1_correct_product",
        "name": "1. Correct Product",
        "description": "Matching SKU, opened unused packaging, all parts present, pristine body.",
        "sku": "SKU-LAMP-LED",
        "observed_state": "opened_unused",
        "parts_missing": "",
        "identity_match": "yes",
        "defect_type": "",
        "expected_checks": {"identity": "PASS", "completeness": "PASS", "condition": "PASS"},
        "expected_disposition": "restock",
    },
    {
        "id": "tc2_wrong_product",
        "name": "2. Wrong Product",
        "description": "Returned item does not match ordered SKU.",
        "sku": "SKU-LAMP-LED",
        "observed_state": "opened_unused",
        "parts_missing": "",
        "identity_match": "no",
        "defect_type": "Wrong merchandise returned",
        "expected_checks": {"identity": "FAIL"},
        "expected_disposition": "pending_review",
    },
    {
        "id": "tc3_empty_box",
        "name": "3. Empty Box",
        "description": "Empty box returned with no product or components inside.",
        "sku": "SKU-LAMP-LED",
        "observed_state": "opened_unused",
        "parts_missing": "desk lamp, usb cable, clamp, adapter",
        "identity_match": "no",
        "defect_type": "Empty parcel returned",
        "expected_checks": {"identity": "FAIL", "completeness": "FAIL"},
        "expected_disposition": "pending_review",
    },
    {
        "id": "tc4_blurry_image",
        "name": "4. Blurry Image",
        "description": "Severely blurred or occluded image preventing visual inspection.",
        "sku": "SKU-LAMP-LED",
        "observed_state": "uncertain",
        "parts_missing": "",
        "identity_match": "uncertain",
        "defect_type": "Occluded visual inspection",
        "expected_checks": {"condition": "UNCERTAIN"},
        "expected_disposition": "pending_review",
    },
    {
        "id": "tc5_damaged_product",
        "name": "5. Damaged Product",
        "description": "Cracked lamp body, broken arm, shattered LED panel.",
        "sku": "SKU-LAMP-LED",
        "observed_state": "damaged",
        "parts_missing": "",
        "identity_match": "yes",
        "defect_type": "Cracked arm and fractured LED panel",
        "expected_checks": {"condition": "FAIL"},
        "expected_disposition": "dispose",
    },
    {
        "id": "tc6_missing_component",
        "name": "6. Missing Component",
        "description": "Lamp present and operational, but essential USB cable is missing.",
        "sku": "SKU-LAMP-LED",
        "observed_state": "opened_unused",
        "parts_missing": "usb cable",
        "identity_match": "yes",
        "defect_type": "Missing USB power cable",
        "expected_checks": {"completeness": "FAIL"},
        "expected_disposition": "refurbish",
    },
    {
        "id": "tc7_multiple_products",
        "name": "7. Multiple Products",
        "description": "Multiple disparate products packed into a single return parcel.",
        "sku": "SKU-LAMP-LED",
        "observed_state": "uncertain",
        "parts_missing": "",
        "identity_match": "uncertain",
        "defect_type": "Multiple mixed items in package",
        "expected_checks": {"identity": "UNCERTAIN"},
        "expected_disposition": "pending_review",
    },
]


@app.get("/internal/test-cases")
def internal_test_cases(request: Request, format: Optional[str] = None):
    """Hidden route for internal adversarial testing and verification."""
    if format == "json" or "application/json" in request.headers.get("accept", ""):
        return ADVERSARIAL_CASES

    cases_html = "".join([
        f"""
        <div class="test-card" id="card_{c['id']}">
          <div class="card-header">
            <div>
              <h3 class="test-title">{c['name']}</h3>
              <p class="test-desc">{c['description']}</p>
            </div>
            <button class="btn-run" onclick="runCase('{c['id']}')">Run Case</button>
          </div>
          <div class="expected-bar">
            <span>Expected Checks: <code>{', '.join([f'{k}: {v}' for k, v in c['expected_checks'].items()])}</code></span>
            <span class="badge-exp">Expected: <strong>{c['expected_disposition'].upper()}</strong></span>
          </div>
          <div class="result-area hidden" id="res_{c['id']}"></div>
        </div>
        """
        for c in ADVERSARIAL_CASES
    ])

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Internal Adversarial Test Suite · Returns Manager</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    .header {{ margin-bottom: 2rem; border-bottom: 1px solid #334155; padding-bottom: 1.5rem; }}
    .title {{ font-size: 1.6rem; font-weight: 800; color: #38bdf8; margin: 0 0 0.5rem; }}
    .subtitle {{ color: #94a3b8; font-size: 0.9rem; margin: 0; }}
    .test-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; }}
    .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }}
    .test-title {{ margin: 0 0 0.35rem; font-size: 1.05rem; color: #f1f5f9; }}
    .test-desc {{ margin: 0; font-size: 0.82rem; color: #94a3b8; }}
    .btn-run {{ background: #0284c7; color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; font-weight: 600; cursor: pointer; }}
    .btn-run:hover {{ background: #0369a1; }}
    .expected-bar {{ display: flex; justify-content: space-between; align-items: center; background: #0f172a; padding: 0.6rem 0.85rem; border-radius: 6px; font-size: 0.8rem; color: #cbd5e1; margin-top: 0.85rem; }}
    .badge-exp {{ background: #334155; padding: 0.2rem 0.6rem; border-radius: 4px; }}
    .result-area {{ margin-top: 0.85rem; padding: 0.85rem; background: #0f172a; border-radius: 6px; font-size: 0.82rem; }}
    .hidden {{ display: none; }}
    .status-pass {{ color: #4ade80; font-weight: 700; }}
    .status-fail {{ color: #f87171; font-weight: 700; }}
    .nav-link {{ display: inline-block; margin-bottom: 1rem; color: #38bdf8; text-decoration: none; font-size: 0.85rem; }}
    .nav-link:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="container">
    <a href="/" class="nav-link">← Return to Operator Console</a>
    <div class="header">
      <h1 class="title">Internal Adversarial Test Suite</h1>
      <p class="subtitle">Confidential harness for verifying edge-case routing, quality thresholds, and fail-safe policy behaviors.</p>
    </div>
    {cases_html}
  </div>
  <script>
    async function runCase(caseId) {{
      const resBox = document.getElementById("res_" + caseId);
      resBox.className = "result-area";
      resBox.innerHTML = "Executing test case against inspection pipeline...";
      try {{
        const res = await fetch("/internal/run-test/" + caseId, {{ method: "POST" }});
        const data = await res.json();
        const dispMatch = data.actual_disposition === data.expected_disposition;
        resBox.innerHTML = `
          <div><strong>Actual Disposition:</strong> <span class="${{dispMatch ? 'status-pass' : 'status-fail'}}">${{data.actual_disposition.toUpperCase()}}</span> (Expected: ${{data.expected_disposition.toUpperCase()}})</div>
          <div style="margin-top: 0.35rem;"><strong>Checks:</strong> ${{data.check_verdicts.join(", ")}}</div>
          <div style="margin-top: 0.35rem;"><strong>Reason:</strong> ${{data.outcome_reason}}</div>
          <div style="margin-top: 0.35rem; color: ${{dispMatch ? '#4ade80' : '#f87171'}}"><strong>Verification:</strong> ${{dispMatch ? '✅ PASSED — Aligned with Policy' : '❌ DISCREPANCY'}}</div>
        `;
      }} catch (err) {{
        resBox.innerHTML = '<span class="status-fail">Error: ' + err.message + '</span>';
      }}
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.post("/internal/run-test/{test_id}")
def internal_run_test(test_id: str):
    """Executes a single adversarial test case and validates against expected outputs."""
    case = next((c for c in ADVERSARIAL_CASES if c["id"] == test_id), None)
    if not case:
        raise HTTPException(status_code=404, detail="Test case not found")

    unit_id = f"UNIT-ADV-{test_id.upper()[:8]}"
    order_id = f"ORD-ADV-{test_id.upper()[:8]}"
    req = InspectionRequest(
        unit_id=unit_id,
        order_id=order_id,
        ordered_sku=case["sku"],
        ordered_asin="B0TESTADV1",
        organization_id="org_returns_inspection",
    )
    observed = {
        "observed_state": case["observed_state"],
        "parts_missing": case["parts_missing"],
        "identity_match": case["identity_match"],
        "defect_type": case["defect_type"],
        "wrong_item_detected": case["identity_match"] == "no",
        "has_missing_evidence": bool(case["parts_missing"]),
        "unclear_evidence": case["observed_state"] == "uncertain" or case["identity_match"] == "uncertain",
    }

    record = pipeline.process_inspection(req, observed_labels=observed)
    check_summaries = [f"{c.check_key.capitalize()}={c.verdict.value}" for c in record.checks]

    return {
        "test_id": test_id,
        "name": case["name"],
        "actual_disposition": record.outcome.decision.value,
        "expected_disposition": case["expected_disposition"],
        "disposition_match": record.outcome.decision.value == case["expected_disposition"],
        "check_verdicts": check_summaries,
        "outcome_reason": record.outcome.reason,
        "record_id": record.record_id,
    }


frontend_path = Path(__file__).resolve().parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=port, reload=False)

