# Cube Buildathon · 04 · Returns Manager

> **Production-grade AI Returns Inspection & Disposition Agent.**
> Step 4 of 5 in the Cube automated commerce chain (preceding Recovery Manager).

[![Tests](https://img.shields.io/badge/pytest-16%20passed-brightgreen.svg)]()
[![Evaluation](https://img.shields.io/badge/eval%20accuracy-100%25-success.svg)]()
[![Schema](https://img.shields.io/badge/schema%20version-2.0.0-blue.svg)]()
[![Tenancy](https://img.shields.io/badge/tenancy-isolated-blueviolet.svg)]()

---

## 1. Highlights & Capabilities

- **Modular Agent Pipeline:**
  - **Identity Agent:** Strict SKU/ASIN verification against catalogue and visual package labels. Outputs `PASS`, `FAIL`, or `UNCERTAIN`. Never guesses.
  - **Completeness Agent:** Compares expected BOM components against visible return items. Marks missing **only with affirmative evidence**.
  - **Condition Agent:** Adheres strictly to the **official Amazon condition taxonomy** (`New`, `Used - Like New`, `Used - Very Good`, `Used - Good`, `Used - Acceptable`, `Unacceptable`, `UNCERTAIN`). Never invents custom condition labels.
  - **Disposition Engine:** Strictly outputs one of: `restock`, `refurbish`, `liquidate`, `dispose`, `pending_review`.
- **Official Evidence Contract:** Emits structured JSON adhering to the Buildathon interoperability contract with deterministic SHA-256 tamper-evident content hashing.
- **Fail-Open Resilience:** Catches model/system exceptions, preserves raw inputs, routes to `pending_review`, and ensures zero data loss.
- **Multi-Tenant Isolation:** Complete isolation between `org_demo_alpha` and `org_demo_bravo`. Cross-tenant queries return 404.
- **Auditable Supervisor Overrides:** Overrides capture original verdict, revised verdict, operator ID, and justification reason without erasing history.
- **High-Density Warehouse Operator UI:** Fast, responsive workstation UI with 1-click demo scenario presets and live evaluation viewer.

---

## 2. 50-Unit Benchmark Evaluation Results

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

## 3. Quick Start & Execution

### Prerequisites
- Python 3.10+
- Dependencies installed: `fastapi`, `uvicorn`, `pydantic`, `pytest`

### 1. Launch the Server & Warehouse UI
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
Open your browser to: **`http://127.0.0.1:8000`**

### 2. Run Automated Test Suite
```bash
pytest tests/test_suite.py -v
```

---

## 4. API Endpoints

- `GET /api/health` — Service health & pipeline state
- `GET /api/products` — Product catalogue with BOM specifications
- `POST /api/inspect` — Run Identity, Completeness, Condition, and Disposition pipeline
- `GET /api/records?org_id={tenant}` — Tenant-isolated evidence records
- `POST /api/override` — Supervisor disposition override with reason code
- `GET /api/eval/run` — Execute 50-unit evaluation benchmark

---

## 5. Architectural Documentation
For in-depth architectural details, sequence diagrams, and schema specifications, see [`ARCHITECTURE.md`](ARCHITECTURE.md).
