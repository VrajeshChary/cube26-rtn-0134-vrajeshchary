# Engineering Invariants, Durable Constraints & Rules (CLAUDE.md)

**System:** CUBE-04 Returns Manager  
**Author:** Vrajesh Chary  
**Scope:** Architecture invariants, safety rules, and operational constraints for developers and AI agents.

---

## 1. Non-Negotiable Engineering Invariants

### Invariant 1: Zero Restock False Positives
Defective, broken, unsealed consumable, incomplete, or swapped items must **NEVER** receive a `RESTOCK` disposition.
- Restocking defective merchandise damages customer trust and incurs double return costs.
- If there is any doubt regarding condition or completeness, the system must divert to `PENDING_REVIEW` or `REFURBISH`.

### Invariant 2: The Affirmative Proof Rule
- Never assume an unobserved component is present.
- Never assume an unobserved component is missing.
- If packaging, glare, or camera angles prevent visual confirmation of a required Bill of Materials (BOM) part, the Completeness Agent must return `UNCERTAIN`.
- Missing status requires affirmative visual evidence of absence (e.g., an empty molded accessory slot) or explicit operator confirmation.

### Invariant 3: Non-Product Media Rule
When an uploaded image is identified as non-product media (logo, screenshot, document, graphic, invoice, receipt, shipping label, or blank frame):
- `physical_product_detected` must be set to `False`.
- The Identity verdict must be `FAIL` or `UNCERTAIN`.
- The final disposition must strictly be `PENDING_REVIEW`.
- The mandatory reasoning must be:  
  **`"Invalid return image: non-product media detected. Manual review required."`**
- Forbidden: Never describe non-product media as "wrong item returned" or "product mismatch".

### Invariant 4: Physical Mismatch Rule
When a physical product is returned that does not match the ordered catalog specification (e.g., sneakers returned instead of an LED desk lamp):
- The Identity verdict must be `FAIL`.
- The final disposition must strictly be `PENDING_REVIEW`.
- The reasoning must start with:  
  **`"Product mismatch / wrong item returned: ..."`**

### Invariant 5: Amazon Condition Taxonomy Compliance
All condition grading must strictly map to official Amazon Condition Guidelines:
1. `New`
2. `Used - Like New`
3. `Used - Very Good`
4. `Used - Good`
5. `Used - Acceptable`
6. `Unacceptable`
7. `UNCERTAIN`
- Forbidden: Never invent custom condition labels such as "Fair", "Refurbished-Grade-A", or "Damaged-Light".

### Invariant 6: Consumable Hygiene & Safety Rule
- Consumable products (Beauty, Personal Care, Health, Household) with opened seals, torn tamper foil, or damaged packaging are biological/hygiene hazards.
- They must immediately receive condition `Unacceptable` and disposition `DISPOSE`.
- Resale or refurbishment of opened consumables is strictly prohibited.

### Invariant 7: Fail-Open Architecture
- No return record may ever be silently dropped or deleted due to an upstream failure (e.g., Gemini API timeout, network drop, or database transient error).
- Failed dependencies must preserve all captured metadata, flag the record as `failed_open` or `pending_review`, and escalate to supervisor bench review.

### Invariant 8: No Barcode Scanner Assumptions
- Do not assume physical barcode scanner hardware exists on inspection benches.
- Return fraud frequently involves putting wrong items inside genuine labeled boxes.
- Verification must rely on physical photographic evidence of the actual item.

### Invariant 9: Multi-Tenant Data Isolation
- Every storage lookup and API response must filter strictly by `organization_id`.
- Tenant A (`org_demo_alpha`) must never see or infer records belonging to Tenant B (`org_demo_bravo`).
- Predictable record IDs cannot be used to bypass tenant access control.

### Invariant 10: Cryptographic Audit Seal
- Every evidence record must calculate a deterministic SHA-256 hash across `record_id`, `organization_id`, `client_id`, `subject`, `checks`, `outcome`, `operator_label`, and `overrides`.
- Overriding a decision requires supervisor credentials and mandatory rationale, appending to the immutable `overrides` audit array.

---

## 2. Forbidden Language & Logic

1. **Forbidden:** `fake_fallback_enabled = True` — Mock models generating synthetic products are strictly prohibited.
2. **Forbidden:** Hardcoding PASS verdicts without evidence.
3. **Forbidden:** Treating `UNCERTAIN` as a failure. `UNCERTAIN` is a valid, first-class safety outcome.
4. **Forbidden:** Silently swallowing errors with bare `except: pass`.
