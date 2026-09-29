# Backend Agent Runbook: CUBE Returns Manager (CUBE-04)

**Module:** `backend/`  
**Framework:** FastAPI + Python 3.13 + Uvicorn  
**AI Engine:** Google Gemini 2.5 Flash (`google/gemini-2.5-flash`)  
**Author:** Vrajesh Chary  

---

## 1. System Requirements & Setup

### Prerequisites
- Python 3.10 or higher (tested on Python 3.13)
- Pip / virtualenv

### Environment Configuration
The backend requires an API key for multimodal computer vision inspection. In the project root, configure your `.env` file:

```bash
# OpenRouter API Key (Supports google/gemini-2.5-flash)
OPENROUTER_API_KEY=your_api_key_here

# Alternatively, Google Generative AI direct key:
GEMINI_API_KEY=your_api_key_here
```

*Note: If no API key is provided, the Vision Agent safely returns an `UNCERTAIN` failure state under Fail-Open policies; it will never invent synthetic products.*

---

## 2. Launching the Backend Service

To start the FastAPI server and warehouse operator workstation:

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Once running, access:
- **Warehouse Operator Workstation UI:** `http://127.0.0.1:8000/`
- **Interactive OpenAPI Documentation:** `http://127.0.0.1:8000/docs`
- **Health & Diagnostic Check:** `http://127.0.0.1:8000/api/health`

---

## 3. Running Automated Tests

Run the full automated test suite containing 21 comprehensive integration and unit tests:

```bash
pytest tests/test_suite.py -v
```

### Verified Test Suite Results
- **Collected:** 21 items
- **Passed:** 21 items (100% pass rate in ~4.9 seconds)
- **Coverage:**
  - Health check & product catalogue verification.
  - Factory-sealed restock pipeline.
  - Missing accessory refurbish pipeline.
  - Broken/damaged unit disposal pipeline.
  - Ambiguous image uncertainty handling.
  - Multi-tenant data isolation (`org_demo_alpha` vs `org_demo_bravo`).
  - SHA-256 tamper-evident hash verification.
  - Supervisor override persistence.
  - 5-dimension semantic identity matching.
  - Non-product media discrimination.

---

## 4. Running the 50-Unit Benchmark Evaluation

Execute the benchmark evaluation harness directly from the command line:

```bash
python evaluation/run_eval.py
```

### Verified Benchmark Output
```text
============================================================
      CUBE 04 — RETURNS MANAGER EVALUATION REPORT
============================================================
Total Evaluated Units : 50
Dual Human Agreement : 100.0%
------------------------------------------------------------
Identity Accuracy    : 100.0%
Completeness Accuracy: 100.0%
Condition Accuracy   : 90.0%
Disposition Accuracy : 100.0%
------------------------------------------------------------
Uncertainty Rate     : 14.0% (7/50 cases safely reviewed)
Restock False Pos.   : 0 (Crucial: 0 defective items restocked)
Restock False Neg.   : 0
Latency (mean / p95) : 0.1 ms / 1.0 ms
============================================================
[SUCCESS] All 50 benchmark cases aligned with policy ground truth!
============================================================
```

---

## 5. API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Returns service health, tenant isolation status, and active Gemini Vision provider state. |
| `GET` | `/api/products` | Retrieves all product catalogue definitions with full Bill of Materials (BOM) specifications. |
| `POST` | `/api/inspect` | Ingests return package photograph and operator labels; executes full multi-agent pipeline and returns `EvidenceRecord`. |
| `GET` | `/api/records?org_id={tenant}` | Retrieves tenant-isolated historical inspection records. |
| `POST` | `/api/override` | Allows an authorized supervisor to override an AI disposition with required reason code. |
| `GET` | `/api/eval/run` | Triggers the 50-unit evaluation benchmark programmatically and returns JSON metrics. |

---

## 6. Multi-Tenant Partitioning Rules

- All evidence records stored in `backend/storage.py` require an explicit `organization_id`.
- The storage layer guarantees that an operator logged into `org_demo_alpha` cannot read or list records belonging to `org_demo_bravo`.
- Querying `/api/records?org_id=org_demo_alpha` returns only records strictly partitioned for that tenant.
