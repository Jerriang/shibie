from dataclasses import dataclass


@dataclass
class AuditChainRow:
    id: int
    action: str
    target_type: str
    target_id: str
    operator_id: int | None
    created_at_iso: str
    prev_hash: str | None
    self_hash: str | None


def verify_chain(rows: list[AuditChainRow], hash_fn) -> tuple[bool, int | None]:
    prev = None
    for row in rows:
        expected = hash_fn(prev, row.action, row.target_type, row.target_id, row.operator_id, row.created_at_iso)
        if row.prev_hash != prev or row.self_hash != expected:
            return False, row.id
        prev = row.self_hash
    return True, None
