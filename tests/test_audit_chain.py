from app.services.hash_chain import chain_hash
from app.services.audit import AuditChainRow, verify_chain


def test_verify_chain_ok():
    h1 = chain_hash(None, "a1", "t", "1", 1, "2026-01-01T00:00:00")
    h2 = chain_hash(h1, "a2", "t", "2", 1, "2026-01-01T00:01:00")

    rows = [
        AuditChainRow(1, "a1", "t", "1", 1, "2026-01-01T00:00:00", None, h1),
        AuditChainRow(2, "a2", "t", "2", 1, "2026-01-01T00:01:00", h1, h2),
    ]
    ok, broken = verify_chain(rows, chain_hash)
    assert ok is True
    assert broken is None


def test_verify_chain_broken():
    h1 = chain_hash(None, "a1", "t", "1", 1, "2026-01-01T00:00:00")
    rows = [
        AuditChainRow(1, "a1", "t", "1", 1, "2026-01-01T00:00:00", None, h1),
        AuditChainRow(2, "a2", "t", "2", 1, "2026-01-01T00:01:00", "bad", "bad"),
    ]
    ok, broken = verify_chain(rows, chain_hash)
    assert ok is False
    assert broken == 2
