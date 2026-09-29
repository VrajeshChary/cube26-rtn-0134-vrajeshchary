# VrajeshChary · Returns Manager (CUBE-04)

Welcome to the official Round 2 submission for **Cube Buildathon — 04 · Returns Manager** by **Vrajesh Chary**.

This repository contains an autonomous, policy-governed returns inspection agent and warehouse operator workstation. The system verifies customer return packages against product catalog definitions using real multimodal computer vision (Google Gemini 2.5 Flash), grades items according to the official Amazon Condition Taxonomy, executes deterministic commercial disposition routing, and seals every inspection with a cryptographic SHA-256 evidence record.

---

## Layout

```
submissions/VrajeshChary/
├── README.md            ← index file: links to all deliverables, status, metrics
├── 01-customer-letter.md ← customer letter to warehouse operations leadership
├── 02-prfaq.md          ← PR/FAQ including tough operational questions
├── 03-one-pager.md      ← executive one-pager with metrics and kill condition
├── CLAUDE.md            ← durable engineering rules, constraints, and forbidden logic
├── build-brief.md       ← technical specifications and functional requirements
├── build-log.md         ← engineering build log tracking development steps
├── eval-report.md       ← 50-unit evaluation report with dual-annotator agreement
├── contract/
│   └── evidence-record.md ← JSON evidence record specification and SHA-256 seal
└── agent/
    └── README.md          ← backend agent runbook and execution instructions
```

---

## 1. Submission Documents Index

Every required submission deliverable is documented below:

| Document | Purpose & Description |
|---|---|
| [**01-customer-letter.md**](01-customer-letter.md) | Working Backwards letter to Warehouse Operations Executives detailing business impact and fraud reduction. |
| [**02-prfaq.md**](02-prfaq.md) | Press release and detailed answers to tough operational questions. |
| [**03-one-pager.md**](03-one-pager.md) | Executive system one-pager with system architecture and verified benchmark metrics. |
| [**CLAUDE.md**](CLAUDE.md) | Invariant engineering rules, durable constraints, and forbidden logic. |
| [**build-brief.md**](build-brief.md) | Complete technical brief, agent definitions, and system requirements. |
| [**build-log.md**](build-log.md) | Comprehensive engineering diary documenting the development journey from setup to final audit. |
| [**eval-report.md**](eval-report.md) | 50-unit evaluation benchmark report evaluated against dual independent human annotators. |
| [**contract/evidence-record.md**](contract/evidence-record.md) | Complete JSON schema and field-by-field specification of the tamper-evident evidence contract. |
| [**agent/README.md**](agent/README.md) | Operational runbook explaining how to start the backend, run tests, and execute benchmarks. |

---

## 2. Project Status & Deliverables

| Face | Deliverable | Status |
|---|---|:---:|
| 1 | Customer Letter, PR/FAQ, One-Pager | ☑ Complete |
| 2 | Invariants & Rules (`CLAUDE.md`) | ☑ Complete |
| 3 | Headless Agent & Multi-Agent Pipeline | ☑ Complete |
| 4 | 50-Unit Benchmark Evaluation Report | ☑ Complete |
| 5 | Warehouse Workstation UI & Live Evidence Display | ☑ Complete |
| 6 | Cross-Pod Cryptographic Evidence Contract | ☑ Complete |

---

## 3. Kill Condition

> **Non-Negotiable Production Invariant:**  
> **If Restock False Positives > 0 on defective, broken, incomplete, or swapped merchandise, the deployment is immediately halted.**  
> *(Current measured benchmark: 0 Restock False Positives across all 50 test cases).*

---

## 4. Key Performance Highlights

- **Automated Test Suite:** 21 / 21 unit & integration tests passing (`pytest tests/test_suite.py`).
- **50-Unit Held-Out Benchmark:** 100.0% Disposition Accuracy, 100.0% Dual Human Agreement (`python evaluation/run_eval.py`).
- **False Positive Restocks:** **0** (Zero defective, damaged, or mismatched goods cleared for restock).
- **Computer Vision:** Genuine multimodal inference via `google/gemini-2.5-flash` with zero mock fallbacks.
- **Fail-Open Architecture:** 14.0% of ambiguous returns safely routed to supervisor review (`PENDING_REVIEW`).
- **Average Pipeline Latency:** < 1 ms average execution for deterministic policy checks.

---

## 5. System Architecture

The Returns Manager pipeline operates as an orchestrated multi-agent system enforcing the affirmative proof rule:

```text
                     [ Return Parcel Photo ]
                                │
                                ▼
            ┌────────────────────────────────────────┐
            │   Vision Agent (Gemini 2.5 Flash)      │
            │   - Blur & edge variance guard         │
            │   - Observable feature extraction      │
            └───────────────────┬────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
 ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
 │Identity Agent│        │ Completeness │        │  Condition   │
 │- 5-D Match   │        │    Agent     │        │    Agent     │
 │- Swaps/Media │        │- BOM Check   │        │- Amazon Tiers│
 └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
            ┌────────────────────────────────────────┐
            │   Disposition Engine (Priority Rules)  │
            │   P0: Non-product media -> REVIEW      │
            │   P1: Wrong item        -> REVIEW      │
            │   P2: Damaged/broken    -> DISPOSE     │
            │   P3: Uncertainty       -> REVIEW      │
            │   P4: Missing parts     -> REFURBISH   │
            │   P5: Pristine sealed   -> RESTOCK     │
            └───────────────────┬────────────────────┘
                                │
                                ▼
            ┌────────────────────────────────────────┐
            │    Cryptographic Evidence Record       │
            │    - Deterministic SHA-256 seal        │
            │    - Tenant-isolated persistence       │
            └────────────────────────────────────────┘
```

---

## 6. How to Run

### 1. Prerequisites & Environment
Ensure Python 3.10+ is installed. In the project root, create your `.env` configuration:

```bash
# Add your Gemini or OpenRouter key to .env:
OPENROUTER_API_KEY=sk-or-v1-your-key-here
VISION_MODEL=google/gemini-2.5-flash
```

### 2. Launch the Application & Workstation UI
```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
- **Operator Workstation:** Open your browser to [`http://127.0.0.1:8000`](http://127.0.0.1:8000)
- **API Documentation:** Interactive Swagger docs at [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs)
- **Health & Telemetry:** [`http://127.0.0.1:8000/api/health`](http://127.0.0.1:8000/api/health)

### 3. Run Automated Tests
```bash
pytest tests/test_suite.py -v
```
*(Verified: 21 / 21 tests passing in ~6 seconds).*

### 4. Run the 50-Unit Benchmark Evaluation
```bash
python evaluation/run_eval.py
```
*(Verified: 50 / 50 benchmark cases passing, 0 false restocks, 100% dual human agreement).*

---

## 7. Warehouse Operator Workstation Demo

The repository includes a production-grade, zero-dependency operator workstation interface served at `http://127.0.0.1:8000`:
- **Visual Intake Bench:** Drag-and-drop or select sample return photos (e.g. `data/real_return_desk_lamp.jpg`).
- **Live Pipeline Trace:** Real-time visual progress showing: Input Evidence → Vision Analysis → Identity Check → Completeness Check → Condition Assessment → Final Disposition.
- **Evidence Integrity Panel:** Instant SHA-256 cryptographic verification and raw JSON evidence record download.
- **Supervisor Override Facility:** Auditable override workflow requiring operator ID and mandatory justification code.
- **Interactive Evaluation Runner:** 1-click modal execution of the 50-unit evaluation suite directly from the UI header.

