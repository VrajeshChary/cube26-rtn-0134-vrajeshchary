# Evidence Record Contract Specification (CUBE-04)

**Contract Version:** `2.0.0`  
**Standard:** Official CUBE Inter-Pod Evidence Contract  
**Author:** Vrajesh Chary (Pod 04 — Returns Manager)  

---

## 1. Overview & Purpose

The **Evidence Record** is the official interoperability contract between the Returns Manager (Pod 04) and downstream warehouse systems (including Recovery Manager, inventory management, and dispute settlement). 

Every inspection performed by CUBE Returns Manager generates a standardized, machine-readable JSON record containing:
1. Product identification and customer order details.
2. Independent verdicts from specialized AI agents (`identity`, `completeness`, `condition`, `vision_evidence`).
3. Hierarchical commercial disposition decision (`RESTOCK`, `REFURBISH`, `LIQUIDATE`, `DISPOSE`, `PENDING_REVIEW`).
4. Human supervisor override audit trails.
5. Deterministic SHA-256 cryptographic proof seal.

---

## 2. Complete Example JSON Evidence Record

```json
{
  "record_id": "RTN-7E82C4A1",
  "schema_version": "2.0.0",
  "organization_id": "org_demo_alpha",
  "client_id": "client_warehouse_central",
  "agent": "cube-04-returns-manager",
  "subject": {
    "unit_id": "UNIT-84920",
    "order_id": "ORD-592819",
    "sku": "SKU-LAMP-LED",
    "asin": "B0DUMMY357",
    "product_name": "Dimmable Architect LED Desk Lamp with Clamp",
    "category": "Home & Office"
  },
  "captured_at": "2026-09-29T00:15:32.418290+00:00",
  "operator_label": {
    "observed_state": "opened_unused",
    "operator_id": "op_chen_42"
  },
  "images": [
    "data/real_return_desk_lamp.jpg"
  ],
  "checks": [
    {
      "check_key": "identity",
      "verdict": "PASS",
      "confidence": 0.96,
      "detail": {
        "ordered_sku": "SKU-LAMP-LED",
        "ordered_asin": "B0DUMMY357",
        "catalog_title": "Dimmable Architect LED Desk Lamp with Clamp",
        "detected_product": "architect desk lamp with clamp base and swing arm",
        "detected_brand": "OEM / Unbranded",
        "matched_expected": true,
        "is_non_product": false,
        "physical_product_detected": true,
        "evidence": "Semantic identity match verified: Detected item aligns with catalog SKU-LAMP-LED across 5 dimensions."
      },
      "model_version": "identity-agent-v2.0",
      "latency_ms": 14
    },
    {
      "check_key": "completeness",
      "verdict": "PASS",
      "confidence": 0.96,
      "detail": {
        "expected_parts": ["lamp base", "led lamp head", "clamp mount", "usb power cable"],
        "visible_parts": ["lamp base", "led lamp head", "clamp mount", "usb power cable"],
        "confirmed_parts": ["lamp base", "led lamp head", "clamp mount", "usb power cable"],
        "missing_parts": [],
        "evidence": "Vision verified all 4 required components present: lamp base, led lamp head, clamp mount, usb power cable."
      },
      "model_version": "completeness-agent-v2.0",
      "latency_ms": 15
    },
    {
      "check_key": "condition",
      "verdict": "PASS",
      "confidence": 0.94,
      "detail": {
        "amazon_condition": "Used - Like New",
        "observed_state": "opened_unused",
        "evidence": "Visual confirmation of open packaging with zero cosmetic blemishes on product.",
        "official_taxonomy": "Amazon Official Condition Guidelines"
      },
      "model_version": "condition-agent-v2.0",
      "latency_ms": 16
    },
    {
      "check_key": "vision_evidence",
      "verdict": "PASS",
      "confidence": 0.95,
      "detail": {
        "has_image": true,
        "detected_product": "architect desk lamp with clamp base and swing arm",
        "detected_brand": "OEM / Unbranded",
        "visible_parts": ["lamp base", "led lamp head", "clamp mount", "usb power cable"],
        "missing_candidates": [],
        "visible_damage": [],
        "packaging_state": "opened_unused",
        "physical_product_detected": true,
        "model_used": "google/gemini-2.5-flash",
        "inference_source": "gemini_multimodal:google/gemini-2.5-flash",
        "is_gemini_inference": true,
        "is_fallback": false
      },
      "model_version": "vision-agent-v2.0",
      "latency_ms": 420
    }
  ],
  "outcome": {
    "decision": "restock",
    "reason": "Open-box pristine condition with complete components. Cleared for open-box prime restock.",
    "decided_by": "agent:cube-04-returns-manager",
    "decided_at": "2026-09-29T00:15:32.419010+00:00"
  },
  "overrides": [],
  "status": "completed",
  "content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "decision_reasoning": [
    "Visual Evidence: architect desk lamp identified (95% visual confidence, packaging: opened_unused).",
    "Identity Verification (PASS): Semantic identity match verified across 5 dimensions.",
    "Completeness Verification (PASS): All BOM components verified present.",
    "Condition Assessment (PASS): Used - Like New - Visual confirmation of zero cosmetic blemishes.",
    "Disposition Policy: Open-box pristine condition with complete components. Cleared for restock."
  ]
}
```

---

## 3. Field-by-Field Specification

| Field Name | Type | Description |
|---|---|---|
| `record_id` | `string` | Unique immutable return identifier prefixed with `RTN-` (e.g., `RTN-7E82C4A1`). |
| `schema_version` | `string` | Schema specification version (`2.0.0`). |
| `organization_id` | `string` | Multi-tenant isolation key (e.g., `org_demo_alpha`). |
| `client_id` | `string` | Specific warehouse intake location or client account ID. |
| `agent` | `string` | Inspecting system identifier (`cube-04-returns-manager`). |
| `subject` | `object` | Return subject: `unit_id`, `order_id`, `sku`, `asin`, `product_name`, `category`. |
| `captured_at` | `string` | ISO 8601 UTC timestamp of inspection initiation. |
| `operator_label` | `object` | Intake station operator ID and optional observed notes. |
| `images` | `array[string]` | File paths, URIs, or hashes of intake photographs analyzed. |
| `checks` | `array[CheckResult]` | Independent verification results (`identity`, `completeness`, `condition`, `vision_evidence`). |
| `outcome` | `Outcome` | Final routing: `decision` (`restock`, `refurbish`, `liquidate`, `dispose`, `pending_review`), `reason`, `decided_by`, `decided_at`. |
| `overrides` | `array[OverrideRecord]` | Supervisor override audit trail: `original_decision`, `revised_decision`, `reason`, `operator_id`, `overridden_at`. |
| `status` | `string` | Inspection state: `completed`, `pending_review`, or `failed_open`. |
| `content_hash` | `string` | 64-character hexadecimal SHA-256 cryptographic seal. |
| `decision_reasoning`| `array[string]` | Human-readable bulleted rationale for warehouse operators. |

---

## 4. Cryptographic Proof Seal (SHA-256)

To guarantee that inspection records cannot be altered retroactively by unauthorized parties, every `EvidenceRecord` calculates a deterministic SHA-256 content hash:

```python
def calculate_hash(self) -> str:
    """Computes deterministic SHA-256 hash of immutable evidence payload."""
    data_to_hash = {
        "record_id": self.record_id,
        "schema_version": self.schema_version,
        "organization_id": self.organization_id,
        "client_id": self.client_id,
        "agent": self.agent,
        "subject": self.subject.model_dump(),
        "captured_at": self.captured_at,
        "operator_label": self.operator_label,
        "images": self.images,
        "checks": [c.model_dump() for c in self.checks],
        "outcome": self.outcome.model_dump(),
        "overrides": [o.model_dump() for o in self.overrides],
        "status": self.status,
    }
    canonical_json = json.dumps(data_to_hash, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
```

If any field (such as the outcome or a check verdict) is modified outside the approved supervisor override workflow, the recalculation will not match `content_hash`, immediately alerting downstream audit systems to tampering.
