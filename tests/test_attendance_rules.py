from datetime import UTC, datetime, timedelta
import time

from app.services.signature import sign_payload, verify_device_signature
from app.services.attendance import decide_status, is_duplicate, is_late, select_absent_students


def test_decide_status_auto_pass():
    status, _ = decide_status(0.9, 0.9, 0.8)
    assert status == "present"


def test_decide_status_pending_review():
    status, _ = decide_status(0.8, 0.9, 0.8)
    assert status == "pending_review"


def test_decide_status_liveness_failed():
    status, _ = decide_status(0.99, 0.2, 0.8)
    assert status == "liveness_failed"


def test_is_late_true():
    start = datetime.now(UTC).replace(tzinfo=None)
    now = start + timedelta(minutes=11)
    assert is_late(now, start, 10) is True


def test_is_duplicate_true():
    now = datetime.now(UTC).replace(tzinfo=None)
    assert is_duplicate(now - timedelta(minutes=3), now, 5) is True


def test_select_absent_students():
    assert select_absent_students([1, 2, 3, 4], [2, 4]) == [1, 3]


def test_verify_device_signature_ok():
    ts = int(time.time())
    sig = sign_payload("secret123", 1, 2, "nonce-1", ts)
    assert verify_device_signature("secret123", 1, 2, "nonce-1", ts, sig)


def test_verify_device_signature_expired():
    ts = int(time.time()) - 120
    sig = sign_payload("secret123", 1, 2, "nonce-1", ts)
    assert verify_device_signature("secret123", 1, 2, "nonce-1", ts, sig) is False
