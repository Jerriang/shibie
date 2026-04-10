import hashlib
import hmac
import time


def sign_payload(secret: str, session_id: int, user_id: int, nonce: str, ts: int) -> str:
    message = f"{session_id}|{user_id}|{nonce}|{ts}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_device_signature(
    secret: str,
    session_id: int,
    user_id: int,
    nonce: str,
    ts: int,
    signature: str,
    allowed_skew_seconds: int = 60,
) -> bool:
    if abs(int(time.time()) - ts) > allowed_skew_seconds:
        return False
    expected = sign_payload(secret, session_id, user_id, nonce, ts)
    return hmac.compare_digest(expected, signature)
