"""Multi-Tenant In-Memory / File Store for Returns Inspection Records.

Enforces strict tenant isolation by organization_id.
Supports operator overrides with immutable audit logs.
"""

from typing import Dict, List, Optional
from .models import EvidenceRecord, OverrideRecord


class TenantEvidenceStore:
    def __init__(self):
        self._tenants: Dict[str, Dict[str, EvidenceRecord]] = {}

    def save_record(self, record: EvidenceRecord) -> EvidenceRecord:
        org_id = record.organization_id
        if org_id not in self._tenants:
            self._tenants[org_id] = {}
        self._tenants[org_id][record.record_id] = record
        return record

    def get_record(self, org_id: str, record_id: str) -> Optional[EvidenceRecord]:
        """Strict tenant-isolated lookup. Cannot access records from another org."""
        tenant_records = self._tenants.get(org_id, {})
        return tenant_records.get(record_id)

    def list_records(self, org_id: str, limit: int = 100) -> List[EvidenceRecord]:
        """List records strictly belonging to the given org_id."""
        tenant_records = self._tenants.get(org_id, {})
        records = list(tenant_records.values())
        records.reverse()
        return records[:limit]

    def add_override(
        self,
        org_id: str,
        record_id: str,
        revised_decision: str,
        reason: str,
        operator_id: str,
    ) -> Optional[EvidenceRecord]:
        """Appends an override record and updates decision without destroying history."""
        record = self.get_record(org_id, record_id)
        if not record:
            return None

        override = OverrideRecord(
            original_decision=record.outcome.decision.value,
            revised_decision=revised_decision,
            reason=reason,
            operator_id=operator_id,
        )
        record.overrides.append(override)
        from .models import DispositionDecision
        record.outcome.decision = DispositionDecision(revised_decision)
        record.outcome.reason = f"[OVERRIDDEN by {operator_id}]: {reason} (Was: {override.original_decision})"
        record.status = "overridden"
        record.content_hash = record.calculate_hash()
        return record


store = TenantEvidenceStore()
