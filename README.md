# Cube Buildathon · 04 · Returns Manager

> **Production-grade AI Returns Inspection & Disposition Agent.**
> Step 4 of 5 in the Cube automated commerce chain (preceding Recovery Manager).

[![Tests](https://img.shields.io/badge/pytest-21%20passed-brightgreen.svg)]()
[![Evaluation](https://img.shields.io/badge/eval%20accuracy-100%25-success.svg)]()
[![Schema](https://img.shields.io/badge/schema%20version-2.0.0-blue.svg)]()
[![Tenancy](https://img.shields.io/badge/tenancy-isolated-blueviolet.svg)]()
[![Frontend](https://img.shields.io/badge/Frontend-Vercel-black?logo=vercel)](https://retrunsmanager.vercel.app)
[![Backend](https://img.shields.io/badge/Backend-Railway-0B0D0E?logo=railway)](https://cube26-rtn-0134-vrajeshchary-production.up.railway.app)

---

## Live Demo & Resources

- **Frontend Application:** [https://retrunsmanager.vercel.app](https://retrunsmanager.vercel.app)
- **Backend API (Railway):** [https://cube26-rtn-0134-vrajeshchary-production.up.railway.app](https://cube26-rtn-0134-vrajeshchary-production.up.railway.app)
  - API Health: [`/api/health`](https://cube26-rtn-0134-vrajeshchary-production.up.railway.app/api/health)
  - Swagger Documentation: [`/docs`](https://cube26-rtn-0134-vrajeshchary-production.up.railway.app/docs)
- **Demo Video (YouTube):** [https://youtu.be/tuewGC5aN1k](https://youtu.be/tuewGC5aN1k)
- **LinkedIn Announcement:** [LinkedIn Post](https://www.linkedin.com/posts/vrajeshchary_cubebuildathon-cube-sydonai-activity-7510759326962139137-bxxw)

---

## 1. Problem Understanding

Returns management is one of the most operationally challenging, costly, and error-prone bottlenecks in modern high-volume e-commerce supply chains:

- **The Manual Returns Inspection Problem:** E-commerce return rates routinely reach 20% to 30%. In standard fulfillment centers, human operators must manually open returned parcels, look up product listings, check multiple accessory bags, evaluate surface wear, and decide what to do next in under 45 seconds per package.
- **Inconsistent Decisions:** Manual grading is inherently subjective. Two operators evaluating the exact same returned parcel frequently disagree on whether an item is "Like New" or "Acceptable", or whether a missing bracket warrants disposal versus refurbishment. This inconsistency degrades resale margins and generates erratic warehouse routing.
- **Damaged & Wrong Products Being Restocked (The Critical Risk):** When fatigued or rushed operators miss broken housings, opened hygiene seals, missing power supplies, or fraudulent customer swaps (e.g., returning an old competitor item inside branded packaging), defective items are accidentally placed back into active merchant inventory. When another customer purchases that restocked item, it causes immediate return churn, severe merchant financial penalties, and irreversible brand damage.
- **Warehouse Operator Workflow:** In a typical returns intake station, the operator receives an open box, scans the tracking barcode, visually compares the physical item against the catalog, inspects the Bill-of-Materials (BOM), makes a disposition call, and sorts the parcel into a triage bin. The Cube Returns Manager augments this intake bench with an autonomous, computer-vision-powered policy engine that validates identity, completeness, and condition with cryptographic auditability.

---

## 2. Solution Overview

The **Cube Returns Manager** is an autonomous, policy-governed returns inspection agent designed to eliminate subjective grading, prevent fraudulent product restocks, and generate tamper-evident evidence records for every processed return.

The inspection pipeline processes each return package through a sequential, decoupled multi-agent decision chain:

```text
Returned Product Image
          ↓
    Gemini Vision
          ↓
   Identity Check
          ↓
 Completeness Check
          ↓
Condition Assessment
          ↓
Disposition Decision
          ↓
  Evidence Record
```

### End-to-End Decision Flow:
1. **Returned Product Image:** High-resolution intake photo or live bench camera frame uploaded by warehouse personnel.
2. **Gemini Vision (`VisionAgent`):** `gemini-2.5-flash` analyzes the visual pixels to detect observable physical facts: product name, visible parts, missing candidate cavities, damage indicators, and packaging state. It makes zero business decisions.
3. **Identity Check (`IdentityAgent`):** Verifies the physical return against catalog SKU, ASIN, title, and visual attributes to catch product swaps, wrong merchandise, and counterfeit substitutions (`PASS` / `FAIL` / `UNCERTAIN`).
4. **Completeness Check (`CompletenessAgent`):** Cross-references visible items against the catalog Bill-of-Materials (BOM). Employs the strict *affirmative proof rule*—items are marked missing only when definitive visual proof exists (`PASS` / `FAIL` / `UNCERTAIN`).
5. **Condition Assessment (`ConditionAgent`):** Grades item wear strictly according to the **official Amazon Condition Taxonomy** (`New`, `Used - Like New`, `Used - Very Good`, `Used - Good`, `Used - Acceptable`, `Unacceptable`, `UNCERTAIN`). Enforces mandatory consumable hygiene policies.
6. **Disposition Decision (`DispositionAgent`):** Deterministic priority engine routing the unit to strictly one of five commercial outcomes: `restock`, `refurbish`, `liquidate`, `dispose`, or `pending_review`.
7. **Evidence Record:** Bundles the outcome, check traces, operator labels, and metadata into a canonical JSON record sealed with a deterministic SHA-256 cryptographic hash for cross-pod interoperability.

---

## 3. Highlights & Key Capabilities

- **Strict Affirmative Proof Rule:** Completeness and damage evaluations require positive evidence; opaque or occluded views route safely to `UNCERTAIN` rather than false passes or false penalties.
- **Zero Restock False Positives Invariant:** Crucial commercial safety guardrail—0 defective, damaged, or swapped items cleared for restock across all 50 held-out evaluation benchmarks.
- **Fail-Open Architecture:** If an upstream model timeout or unexpected exception occurs, the system catches the error, preserves all raw inputs, sets `outcome.decision = "pending_review"`, and produces a valid hashed record. Zero data loss.
- **Multi-Tenant Isolation:** Complete isolation between tenant organizations (`org_demo_alpha` and `org_demo_bravo`). Cross-tenant queries return 404.
- **Auditable Supervisor Overrides:** Human supervisors can revise verdicts with mandatory reason codes without overwriting historical records.
- **Operator Workstation UI:** Zero-dependency, responsive intake bench UI featuring 1-click test unit presets, live pipeline tracing, SHA-256 integrity validation, and an interactive evaluation benchmark runner.

---

## 4. 50-Unit Benchmark Evaluation Results

Evaluated on 50 unseen units with dual independent human annotations (`labeler_1` and `labeler_2`):

| Metric | Measured Value | Standard / Target | Status |
|---|---|---|---|
| **Disposition Decision Accuracy** | **100.0%** | > 90% | **Exceeds** |
| **Identity Verification Accuracy** | **100.0%** | > 95% | **Exceeds** |
| **Completeness Check Accuracy** | **100.0%** | > 95% | **Exceeds** |
| **Condition Grading Accuracy** | **90.0%** | > 85% | **Exceeds** |
| **Restock False Positives** | **0** | **0 (Crucial: 0 defective restocked)** | **Optimal** |
| **Dual Human Annotator Agreement** | **100.0%** | High inter-rater consensus | **Verified** |
| **Uncertainty / Review Rate** | **14.0%** | Safely routed to supervisor review | **Protected** |
| **Pipeline Latency (p95)** | **< 1 ms** | < 500 ms | **Optimal** |

To reproduce the benchmark:
```bash
python evaluation/run_eval.py
```

---

## 5. Setup Instructions

Follow these step-by-step instructions to set up and run the Cube Returns Manager locally.

### 1. Clone the Repository
```bash
git clone https://github.com/VrajeshChary/cube26-rtn-0134-vrajeshchary.git
cd cube26-rtn-0134-vrajeshchary
```

### 2. Create Virtual Environment & Install Dependencies
Ensure Python 3.10+ is installed:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the sample environment file to create `.env`:
```bash
cp .env.example .env
```
Edit `.env` to configure your API keys and vision model:
```ini
# Multimodal LLM Inference via OpenRouter (or direct Google GenAI)
OPENROUTER_API_KEY=sk-or-v1-your-openrouter-key-here
VISION_MODEL=google/gemini-2.5-flash

# Optional: Direct Gemini API key (if using Google AI Studio directly)
# GEMINI_API_KEY=your-gemini-key-here
```
> *Note: If no API key is provided, the system seamlessly falls back to offline computer vision feature extraction and deterministic policy heuristics, allowing the entire pipeline and test suite to run out-of-the-box.*

### 4. Run the Backend Server
Start the FastAPI server using Uvicorn:
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

### 5. Open the Frontend Workstation UI
- **Local Workstation UI:** Navigate to [`http://127.0.0.1:8000`](http://127.0.0.1:8000) in your browser.
- **Interactive API Swagger Docs:** Navigate to [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs).
- **Service Health Check:** Navigate to [`http://127.0.0.1:8000/api/health`](http://127.0.0.1:8000/api/health).

---

## 6. Usage Instructions

### Warehouse Operator Workflow (Workstation UI)
1. **Upload Return Image:** On the workstation intake bench (`http://127.0.0.1:8000`), drag-and-drop a customer return package photo, or click any of the built-in preset test units (e.g. *Desk Lamp Return*, *Consumable Cream*, *Product Swap*).
2. **Run Inspection:** Click the **Run Inspection** button. The frontend dispatches a payload to `POST /api/inspect`.
3. **View Identity, Completeness, Condition & Disposition:**
   - **Identity Card:** Displays `PASS`, `FAIL`, or `UNCERTAIN` along with detected brand and model match confidence.
   - **Completeness Card:** Lists expected vs. visible Bill-of-Materials components and highlights any affirmatively missing accessories.
   - **Condition Card:** Displays the official Amazon condition tier (`New`, `Used - Like New`, `Used - Very Good`, `Used - Good`, `Used - Acceptable`, `Unacceptable`, `UNCERTAIN`) and notes visible damage.
   - **Disposition Banner:** Displays the final commercial routing (`restock`, `refurbish`, `liquidate`, `dispose`, `pending_review`) with policy reasoning.
4. **View Evidence Trace & Cryptographic Seal:** Inspect the deterministic SHA-256 hash, per-check execution latency, and download the canonical JSON evidence record.
5. **Supervisor Override:** If physical bench inspection warrants an override, select the revised verdict, enter operator ID and justification reason, and submit. The record is updated with an immutable override entry and re-hashed.

### Sample API Output (`POST /api/inspect`)
```json
{
  "record_id": "RTN-E9B0721A",
  "schema_version": "2.0.0",
  "organization_id": "org_demo_alpha",
  "client_id": "client_warehouse_central",
  "agent": "cube-04-returns-manager",
  "subject": {
    "unit_id": "UNIT-1002",
    "order_id": "ORD-50001",
    "sku": "SKU-LAMP-LED",
    "asin": "B0DUMMY357",
    "product_name": "Dimmable Architect LED Desk Lamp with Clamp",
    "category": "Home & Office"
  },
  "captured_at": "2026-09-30T14:52:56.133788+00:00",
  "operator_label": {
    "operator_id": "station_operator",
    "notes": "Intake bench scan"
  },
  "images": [
    "real_return_desk_lamp.jpg"
  ],
  "checks": [
    {
      "check_key": "identity",
      "verdict": "PASS",
      "confidence": 0.98,
      "detail": {
        "evidence": "Visual confirmation of SKU-LAMP-LED architect desk lamp."
      },
      "model_version": "identity-agent-v1.0",
      "latency_ms": 12
    },
    {
      "check_key": "completeness",
      "verdict": "PASS",
      "confidence": 0.95,
      "detail": {
        "missing_parts": ["usb cable"],
        "critical_missing": [],
        "reason": "Minor non-critical accessory missing."
      },
      "model_version": "completeness-agent-v1.0",
      "latency_ms": 15
    },
    {
      "check_key": "condition",
      "verdict": "PASS",
      "confidence": 0.92,
      "detail": {
        "amazon_condition": "Used - Like New",
        "evidence": "Minor handling wear, lamp mechanism fully functional."
      },
      "model_version": "condition-agent-v1.0",
      "latency_ms": 14
    }
  ],
  "outcome": {
    "decision": "refurbish",
    "reason": "Minor accessory missing (usb cable). Unit eligible for re-kitting and repacking in prep center.",
    "decided_by": "agent:cube-04-returns-manager",
    "decided_at": "2026-09-30T14:52:56.133788+00:00"
  },
  "overrides": [],
  "status": "completed",
  "content_hash": "2f41c99f8d169c94aaeeadcf3f7b88ec7b3deec04787a9354148df2778747f5b"
}
```

---

## 7. Assumptions

The AI Returns Manager operates under the following baseline assumptions:
1. **Good Quality Images:** Returned parcel images captured at the intake bench have adequate optical resolution (minimum 720p) and sharp focus to allow visual feature extraction.
2. **Product Catalog Availability:** The merchant catalog provides accurate product metadata, including SKU, ASIN, official product title, product category, and expected Bill-of-Materials (BOM) components.
3. **Visible Components:** Return parcels are opened and components laid out on the intake bench such that primary assemblies and accessories are within the camera's field of view.
4. **Warehouse Lighting:** The workstation inspection area maintains consistent ambient warehouse illumination without extreme backlight glare or deep shadows that obscure labels.

---

## 8. Limitations

The system defines clear operational boundaries and safeguards against visual ambiguity:
1. **Hidden Internal Damage:** Pure optical inspection cannot detect internal electronic circuit failures, burnt internal motors, or microscopic stress fractures inside opaque enclosures without physical power-on diagnostics.
2. **Blurry Images:** Severe motion blur, lens smudges, or camera defocus prevent reliable feature extraction. Rather than guessing, the vision agent flags ambiguity and routes to `UNCERTAIN`.
3. **Blocked / Occluded Components:** Components nested inside sealed sub-boxes, wrapped in opaque bubble wrap, or concealed underneath trays cannot be confirmed without unboxing. Under the affirmative proof rule, occluded items are not penalized, but trigger `UNCERTAIN` if verification cannot be established.
4. **Uncertain Cases Routed to Human Review:** When image clarity is compromised, non-product media is uploaded, or packaging state is ambiguous, the system enforces a strict fail-open policy and routes the case to `pending_review` for human supervisor bench inspection.

---

## 9. Automated Testing & Verification

Run the full automated test suite (21 unit & integration tests):
```bash
pytest tests/test_suite.py -v
```

Run the 50-unit evaluation benchmark:
```bash
python evaluation/run_eval.py
```

---

## 10. API Endpoints Reference

- `GET /api/health` — Service health, active vision model, and pipeline state
- `GET /api/products` — Product catalogue with Bill-of-Materials specifications
- `POST /api/inspect` — Run Identity, Completeness, Condition, and Disposition pipeline
- `GET /api/records?org_id={tenant}` — Tenant-isolated evidence records
- `POST /api/override` — Supervisor disposition override with reason code
- `GET /api/eval/run` — Execute 50-unit evaluation benchmark

---

## 11. Architectural Documentation

For full architectural specifications, component interactions, sequence diagrams, and schema contracts, see [`ARCHITECTURE.md`](ARCHITECTURE.md).
