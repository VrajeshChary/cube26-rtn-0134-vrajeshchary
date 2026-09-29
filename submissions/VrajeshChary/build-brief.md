# Technical Build Brief: CUBE Returns Manager (CUBE-04)

**Document:** Engineering Specifications & Requirements Brief  
**Author:** Vrajesh Chary  
**Release:** v2.0.0 — Production Submission  

---

## 1. Problem Statement & Scope

High-volume e-commerce fulfillment centers receive thousands of customer returns daily. Traditional manual inspection suffers from severe operational bottlenecks:
- **High Latency:** Manual visual inspection takes 45–90 seconds per parcel.
- **Subjective Error:** Human grading varies wildly between operators and shifts.
- **Return Fraud:** Product swapping, wardrobing, and component harvesting cost retailers billions annually.
- **Defective Restocks:** Damaged goods slip through manual checks and get restocked to new buyers.
- **Dispute Vulnerability:** Suppliers and liquidators dispute unverified grading decisions due to a lack of visual proof.

**Scope of CUBE-04:**  
Deliver an autonomous, policy-governed returns inspection agent and operator workstation that performs automated visual verification against catalog specifications, grades items according to Amazon's condition taxonomy, routes items deterministically, and issues tamper-evident SHA-256 evidence records.

---

## 2. Core Functional Requirements

### Requirement 1: Multimodal Vision Feature Extraction
- Ingest physical photographs captured at warehouse intake stations (JPEG, PNG, WebP, Base64).
- Invoke **Google Gemini 2.5 Flash** with a structured, zero-hallucination prompt.
- Extract structured visual features: `detected_product`, `detected_brand`, `visible_parts`, `missing_candidates`, `visible_damage`, `packaging_state`, `confidence`, and `physical_product_detected`.
- Enforce pre-inference image quality checks: detect blurry images (edge variance < 15.0), blank frames, or low resolution (< 16x16px) and return `UNCERTAIN`.

### Requirement 2: Semantic Identity Verification
- Verify that the physical item pictured matches the ordered SKU across 5 dimensions:
  1. Product Category (e.g., Lighting vs Footwear vs Electronics).
  2. Key Components (e.g., clamp arm and lamp socket).
  3. Brand Markings (e.g., OEM markings vs competitor brand).
  4. SKU Metadata Tokens.
  5. Visual Features & Colorways.
- Enforce Non-Product Media Guard: distinguish genuine physical merchandise from logos, screenshots, invoices, and documents.
- Catch cross-catalog SKU swaps (e.g., coffee mug returned when dog leash was ordered).

### Requirement 3: Bill-of-Materials Completeness Verification
- Compare visible components against catalog Bill-of-Materials (`expected_parts` and `critical_parts`).
- Enforce the Affirmative Proof Rule:
  - If all required parts are visually verified -> `PASS`.
  - If an accessory is missing -> `FAIL` (identifying missing part).
  - If parts cannot be seen due to packaging or occlusion -> `UNCERTAIN` (never guess).

### Requirement 4: Amazon Condition Taxonomy Grading
- Strictly evaluate damage, wear, and packaging against the official Amazon Condition Taxonomy:
  - `New`: Intact factory seal, pristine packaging.
  - `Used - Like New`: Open box, zero cosmetic blemishes, complete parts.
  - `Used - Very Good`: Minor packaging blemish or cosmetic mark, fully functional.
  - `Used - Good`: Moderate cosmetic wear from normal use, fully functional.
  - `Used - Acceptable`: Heavy cosmetic wear or deep scratches, fully functional.
  - `Unacceptable`: Structural damage, cracks, broken joints, or unsealed consumable hygiene hazards.
  - `UNCERTAIN`: Insufficient visual evidence to assign a grade.

### Requirement 5: Hierarchical Disposition Engine
Apply deterministic priority routing to assign one of five official dispositions:
- **Priority 0 (Non-Product Media):** -> `PENDING_REVIEW` (`"Invalid return image: non-product media detected. Manual review required."`).
- **Priority 1 (Identity Mismatch):** -> `PENDING_REVIEW` (`"Product mismatch / wrong item returned: ..."`).
- **Priority 2 (Physical Damage):** Structural breakage -> `DISPOSE`. Serviceable blemish -> `REFURBISH`.
- **Priority 3 (Uncertainty / Ambiguity):** Any uncertain check -> `PENDING_REVIEW`.
- **Priority 4 (Missing Parts):** Critical component missing -> `DISPOSE`. Minor accessory missing -> `REFURBISH`.
- **Priority 5 (Condition Tiering):** Sealed `New` -> `RESTOCK`. Open-box pristine -> `RESTOCK` (if restockable open-box permitted). `Used - Good`/`Acceptable` -> `LIQUIDATE`.

### Requirement 6: Tamper-Evident Evidence Contract
- Generate a standardized JSON evidence record adhering to the CUBE schema (`EvidenceRecord`).
- Compute a deterministic SHA-256 content hash over the immutable payload.
- Record operator overrides in an audit array with mandatory supervisor credentials and rationale.

### Requirement 7: Warehouse Operator Workstation UI
- Responsive, high-contrast interface designed for warehouse touchscreens and desktop intake desks.
- Drag-and-drop image intake with live file inspection.
- Real-time agent verdict cards with Amazon condition grading callouts.
- Live SHA-256 seal verification and raw JSON evidence export.
