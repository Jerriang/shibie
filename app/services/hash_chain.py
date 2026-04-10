import hashlib


def chain_hash(prev_hash: str | None, action: str, target_type: str, target_id: str, operator_id: int | None, ts: str) -> str:
    raw = f"{prev_hash or ''}|{action}|{target_type}|{target_id}|{operator_id}|{ts}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
