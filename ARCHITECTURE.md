# Architecture & Engineering Specifications · Cube 04 Returns Manager

## 1. System Overview
The **Returns Manager** is Step 4 in the 5-stage Cube commerce execution chain:
```
Receiving Manager ──▶ Prep Manager ──▶ Pack Manager ──▶ Returns Manager ──▶ Recovery Manager
 (Arrival state)      (Compliance)      (Pack check)     (Inspection/Disp)    (Financial Claim)
```
Its primary objective is fast, consistent, and evidence-backed triage of returned inventory, ensuring high-margin items are safely restocked or refurbished while preventing contaminated or damaged goods from re-entering active merchant inventory.

---

## 2. Multi-Agent Inspection Pipeline & Data Flow

The returns inspection workflow processes incoming return parcels through a sequential, decoupled multi-agent pipeline:

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

### End-to-End Data Flow Sequence
1. **Image Input:** Operator uploads physical return package photos or bench camera feeds via the workstation UI or API.
2. **Vision Model (`VisionAgent`):** `gemini-2.5-flash` analyzes visual pixels and outputs strictly observable physical evidence into structured `image_metadata`.
3. **Identity Agent:** Cross-references detected product name, branding, category, and visual attributes against the catalog SKU and ASIN.
4. **Completeness Agent:** Cross-references visible components against the expected Bill-of-Materials (BOM), requiring affirmative proof for missing items.
5. **Condition Agent:** Evaluates packaging integrity, wear, cosmetic flaws, and structural damage against the official Amazon Condition Taxonomy.
6. **Disposition Agent:** Executes a deterministic priority decision tree to assign the final commercial outcome (`restock`, `refurbish`, `liquidate`, `dispose`, or `pending_review`).
7. **Final Sealed Record:** The outcome and individual check traces are sealed into an immutable `EvidenceRecord` secured with a deterministic SHA-256 content hash.

---

### Component & Agent Responsibilities

#### Agent 0: Vision Evidence Agent (`backend/agents/vision_agent.py`)
- **Role:** Pure observable perception. Analyzes uploaded return photos or base64 streams via Google GenAI (`gemini-2.5-flash` via OpenRouter or direct API) with a local feature extractor fallback.
- **Contract:** Outputs strictly observable facts: `physical_product_detected`, `detected_product`, `detected_brand`, `visible_parts`, `missing_candidates`, `visible_damage`, `packaging_state`, `uncertainty_notes`, and `confidence`.
- **Constraint:** Never makes business or disposition decisions. Never invents missing components or damage without visual justification.
- **Integration:** Emits `image_metadata` to feed Identity, Completeness, and Condition agents.

#### Agent 1: Identity Agent (`backend/agents/identity_agent.py`)
- **Contract:** Outputs `PASS`, `FAIL`, or `UNCERTAIN`. Never guesses.
- **Rules:**
  - `PASS`: Return matches catalog SKU, dimensions, visual features, and product markings.
  - `FAIL`: Clear evidence of fraudulent substitution, product mismatch, or non-product media (e.g. competitor brand, wrong item, blank screen, shipping label).
  - `UNCERTAIN`: Image quality is insufficient, or camera angle prevents definitive SKU confirmation.

#### Agent 2: Completeness Agent (`backend/agents/completeness_agent.py`)
- **Contract:** Outputs `PASS`, `FAIL`, or `UNCERTAIN`.
- **Rules:**
  - `PASS`: All expected BOM parts are confirmed present, or unit is manufacturer-sealed (`factory_sealed`).
  - `FAIL`: Marked missing **only when affirmative evidence exists** (e.g. empty molded cavity in tray, absent power adapter). Differentiates between critical non-replaceable parts and minor replaceable accessories.
  - `UNCERTAIN`: Package interior is opaque or occluded from camera angle without affirmative missing evidence.

#### Agent 3: Condition Agent (`backend/agents/condition_agent.py`)
- **Contract:** Adheres strictly to the **official Amazon Condition Taxonomy**:
  - `New`
  - `Used - Like New`
  - `Used - Very Good`
  - `Used - Good`
  - `Used - Acceptable`
  - `Unacceptable`
  - `UNCERTAIN`
- **Rules:** No custom condition labels. Consumable/hygiene seal breaks (protein powder, face serum) immediately qualify as `Unacceptable`. Ambiguous lighting, glare, or motion blur yields `UNCERTAIN`.

#### Agent 4: Disposition Decision Engine (`backend/agents/disposition_agent.py`)
Routes to **strictly one of five allowed dispositions**:
1. `restock`: Factory sealed brand new items, or complete open-box items permitted under category restock policies.
2. `refurbish`: Pristine units missing minor accessories (e.g., replacement USB cord) or requiring repackaging.
3. `liquidate`: Functional units with moderate cosmetic wear (`Used - Good` / `Used - Acceptable`).
4. `dispose`: Broken units (`Unacceptable`), unsealed consumables, or critical missing parts that cannot be re-kitted.
5. `pending_review`: Any check returning `UNCERTAIN`, identity failure, non-product media, or system fail-open trigger.

---

## 3. Architectural Rationale: Why Multi-Agent?

Rather than submitting a single monolithic LLM prompt that attempts to ingest photos, verify catalog identity, inspect bill-of-materials completeness, grade physical condition, and determine commercial disposition simultaneously, the Cube Returns Manager employs a modular, decoupled multi-agent pipeline. This architecture provides critical engineering benefits:

1. **Separation of Responsibilities & Clean Domain Boundaries:**
   - **Perception vs. Business Policy:** `VisionAgent` acts as a pure sensory organ. Its exclusive responsibility is to observe physical reality and extract factual evidence (`detected_product`, `visible_parts`, `visible_damage`, `packaging_state`, `confidence`). It is strictly forbidden from making business or disposition decisions.
   - **Specialized Reasoning:** Downstream agents (`IdentityAgent`, `CompletenessAgent`, `ConditionAgent`) reason independently within their specific domain contracts without cross-domain pollution.

2. **Lower Hallucination Risk:**
   - Monolithic multimodal prompts asked to perform complex multi-factor business decisions suffer from high hallucination rates—often inventing missing accessories to justify restock denials, or ignoring cosmetic damage to force a positive verdict.
   - By constraining the vision model to objective physical observation and handling business rules deterministically, the hallucination surface area is reduced to near zero.

3. **Independent Validation & Granular Evidence:**
   - Every agent check outputs an isolated `CheckResult` containing its own verdict (`PASS`, `FAIL`, `UNCERTAIN`), confidence score, detailed diagnostic evidence, model version, and execution latency.
   - Operators and auditors can pinpoint the exact stage that triggered a failure or required supervisor review.

4. **Easier Testing & Isolated Verification:**
   - Individual agents can be tested deterministically with unit tests without executing costly multimodal model calls.
   - Edge cases (such as consumable hygiene seal breaches, fraudulent product substitutions, or partial accessory omissions) can be rigorously validated across hundreds of test permutations in milliseconds.

5. **Deterministic Disposition Rules & Non-Negotiable Invariants:**
   - Commercial disposition routing (`restock`, `refurbish`, `liquidate`, `dispose`, `pending_review`) is governed by hard commercial contracts and merchant safety regulations (e.g., zero defective items restocked, mandatory disposal of unsealed cosmetics).
   - Encoding disposition as a deterministic priority engine rather than relying on stochastic LLM temperature ensures 100% reproducible compliance and completely eliminates false restock disasters.

---

## 4. Official Evidence Contract & Tamper-Evident Hashing

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
  "images": ["real_return_desk_lamp.jpg"],
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
The `content_hash` is computed over a canonical JSON serialization of the immutable payload (sorted keys, compact separators). 

### How Human Review & Supervisor Overrides Work
1. When an agent check triggers `UNCERTAIN` or detects a product mismatch/non-product media, the record is placed into `pending_review` status.
2. A human warehouse supervisor examines the unit at the physical inspection bench alongside the AI evidence trace.
3. If an override is approved, the supervisor submits an override payload capturing:
   - `original_decision`
   - `revised_decision`
   - `operator_id`
   - Mandatory `reason` justification code
4. The system appends this immutable audit record to `overrides[]` without erasing original history and re-computes the canonical SHA-256 hash to guarantee non-repudiation.

---

## 5. Engineering Guardrails
1. **Tenancy Isolation (`org_id`):** Multi-tenant store strictly partitions records by `organization_id` (`org_demo_alpha` vs `org_demo_bravo`). Cross-tenant queries return 404.
2. **Fail-Open Architecture:** If an unhandled exception or upstream model service failure occurs, the pipeline catches the error, sets `status = "failed_open"`, preserves all inputs, sets `outcome.decision = "pending_review"`, and produces a valid hashed record. Zero data loss.
3. **UNCERTAIN as First-Class Citizen:** Ambiguous cases never guess. They route directly to `pending_review`.
