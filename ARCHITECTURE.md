# Architecture & Engineering Specifications · Cube 04 Returns Manager

## 1. System Overview
The **Returns Manager** is Step 4 in the 5-stage Cube commerce execution chain:
```
Receiving Manager ──▶ Prep Manager ──▶ Pack Manager ──▶ Returns Manager ──▶ Recovery Manager
 (Arrival state)      (Compliance)      (Pack check)     (Inspection/Disp)    (Financial Claim)
```
Its primary objective is fast, consistent, and evidence-backed triage of returned inventory, ensuring high-margin items are safely restocked or refurbished while preventing contaminated or damaged goods from re-entering active merchant inventory.

---

## 2. Multi-Agent Inspection Pipeline

```
                              [ Return Capture ]
                    (SKU / ASIN / BOM / Observed State / Image)
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   0. Vision Evidence Agent│
                        │ • Multimodal feature scan │
                        │ • Pure observable evidence│
                        │ • No business decisions   │
                        └─────────────┬─────────────┘
                                      │ (image_metadata)
                                      ▼
                        ┌───────────────────────────┐
                        │   1. Identity Agent       │
                        │ • Compares SKU/ASIN to BOM│
                        │ • PASS / FAIL / UNCERTAIN │
                        └─────────────┬─────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   2. Completeness Agent   │
                        │ • Expected vs Visible BOM │
                        │ • Affirmative evidence only│
                        │ • PASS / FAIL / UNCERTAIN │
                        └─────────────┬─────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   3. Condition Agent      │
                        │ • Official Amazon scale   │
                        │ • PASS / FAIL / UNCERTAIN │
                        └─────────────┬─────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   4. Disposition Engine   │
                        │ • Policy-governed router  │
                        │ • 5 Allowed Dispositions  │
                        └─────────────┬─────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │ Evidence & Hash Engine    │
                        │ • SHA-256 Tamper Evidence │
                        │ • Tenant-Isolated Store   │
                        └───────────────────────────┘
```

### Agent 0: Vision Evidence Agent (`backend/agents/vision_agent.py`)
- **Role:** Pure observable perception. Analyzes uploaded return photos or base64 streams via Google GenAI (`gemini-2.5-flash`) or local visual extractor fallback.
- **Contract:** Outputs strictly observable facts: `detected_product`, `detected_brand`, `visible_parts`, `missing_candidates`, `visible_damage`, `packaging_state`, `uncertainty_notes`, and `confidence`.
- **Constraint:** Never makes business or disposition decisions. Never invents missing components or damage.
- **Integration:** Feeds `image_metadata` into Identity, Completeness, and Condition agents.

### Agent 1: Identity Agent
- **Contract:** Outputs `PASS`, `FAIL`, or `UNCERTAIN`. Never guesses.
- **Rules:**
  - `PASS`: Return matches catalog SKU, dimensions, visual features, and product markings.
  - `FAIL`: Clear evidence of fraudulent substitution or mismatch (e.g. competitor brand or cheap generic returned in branded packaging).
  - `UNCERTAIN`: Image quality is insufficient or camera angle prevents definitive SKU confirmation.

### Agent 2: Completeness Agent
- **Contract:** Outputs `PASS`, `FAIL`, or `UNCERTAIN`.
- **Rules:**
  - `PASS`: All BOM parts are confirmed present, or unit is manufacturer-sealed (`factory_sealed`).
  - `FAIL`: Marked missing **only when affirmative evidence exists** (e.g. empty molded cavity in tray, absent power adapter). Differentiates between critical non-replaceable parts and minor replaceable accessories.
  - `UNCERTAIN`: Package interior is opaque or occluded from camera angle without affirmative missing evidence.

### Agent 3: Condition Agent
- **Contract:** Adheres strictly to the official Amazon Condition Taxonomy:
  - `New`
  - `Used - Like New`
  - `Used - Very Good`
  - `Used - Good`
  - `Used - Acceptable`
  - `Unacceptable`
  - `UNCERTAIN`
- **Rules:** No custom condition labels. Consumable/hygiene seal breaks (protein powder, face serum) immediately qualify as `Unacceptable`. Ambiguous lighting/glare yields `UNCERTAIN`.

### Agent 4: Disposition Decision Engine
Routes to **strictly one of five allowed dispositions**:
1. `restock`: Factory sealed brand new items, or complete open-box items permitted under category restock policies.
2. `refurbish`: Pristine units missing minor accessories (e.g., replacement USB cord) or requiring repackaging.
3. `liquidate`: Functional units with moderate cosmetic wear (`Used - Good` / `Used - Acceptable`).
4. `dispose`: Broken units (`Unacceptable`), unsealed consumables, or critical missing parts that cannot be re-kitted.
5. `pending_review`: Any check returning `UNCERTAIN`, identity failure, or system fail-open trigger.

---

## 3. Official Evidence Contract & Tamper-Evident Hashing
All records conform to the schema:
```json
{
  "record_id": "RTN-E9B0721A",
  "schema_version": "2.0.0",
  "organization_id": "org_demo_alpha",
  "client_id": "client_prep_central",
  "agent": "cube-04-returns-manager",
  "subject": {
    "unit_id": "UNIT-1002",
    "order_id": "ORD-50001",
    "sku": "SKU-LAMP-LED",
    "asin": "B0DUMMY357",
    "product_name": "Dimmable Architect LED Desk Lamp with Clamp",
    "category": "Home & Office"
  },
  "captured_at": "2026-09-27T14:52:56.133788+00:00",
  "operator_label": {
    "operator_id": "op_chen",
    "notes": "Bench inspection scan"
  },
  "images": [],
  "checks": [
    {
      "check_key": "identity",
      "verdict": "PASS",
      "confidence": 0.98,
      "detail": {"evidence": "Confirmed visual match against catalog SKU."},
      "model_version": "identity-agent-v1.0",
      "latency_ms": 14
    }
  ],
  "outcome": {
    "decision": "refurbish",
    "reason": "Minor accessory missing (usb cable). Unit eligible for re-kitting in prep center.",
    "decided_by": "agent:cube-04-returns-manager",
    "decided_at": "2026-09-27T14:52:56.133788+00:00"
  },
  "overrides": [],
  "status": "completed",
  "content_hash": "2f41c99f8d169c94aaeeadcf3f7b88ec7b3deec04787a9354148df2778747f5b"
}
```

### Deterministic SHA-256 Content Hash
The `content_hash` is computed over a canonical JSON serialization of the immutable payload. If a supervisor overrides a disposition, the override is appended to `overrides[]` with the supervisor ID, timestamp, and mandatory justification reason, and the record is re-hashed to guarantee non-repudiation.

---

## 4. Engineering Guardrails
1. **Tenancy Isolation (`org_id`):** Multi-tenant store strictly partitions records by `organization_id` (`org_demo_alpha` vs `org_demo_bravo`). Cross-tenant queries return 404.
2. **Fail-Open Architecture:** If an unhandled exception or upstream service failure occurs, the pipeline catches the error, sets `status = "failed_open"`, preserves all inputs, sets `outcome.decision = "pending_review"`, and produces a valid hashed record. Zero data loss.
3. **UNCERTAIN as First-Class Citizen:** Ambiguous cases never guess. They route directly to `pending_review`.
