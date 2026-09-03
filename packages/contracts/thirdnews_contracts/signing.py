"""HMAC request signing, shared by both ends of the classifier protocol."""

from __future__ import annotations

import hashlib
import hmac
import time

SIGNATURE_HEADER = "X-3rdnews-Signature"
TIMESTAMP_HEADER = "X-3rdnews-Timestamp"

#: Requests older than this are rejected, to blunt replay attacks.
DEFAULT_TOLERANCE_S = 300


def _digest(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), digestmod=hashlib.sha256)
    mac.update(timestamp.encode())
    mac.update(b".")
    mac.update(body)
    return mac.hexdigest()


def sign_payload(secret: str, body: bytes, timestamp: int | None = None) -> dict[str, str]:
    """Return the headers that authenticate `body`."""

    ts = str(timestamp if timestamp is not None else int(time.time()))
    return {TIMESTAMP_HEADER: ts, SIGNATURE_HEADER: f"sha256={_digest(secret, ts, body)}"}


def verify_signature(
    secret: str,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    tolerance_s: int = DEFAULT_TOLERANCE_S,
) -> bool:
    if not signature or not timestamp:
        return False
    try:
        age = abs(int(time.time()) - int(timestamp))
    except ValueError:
        return False
    if age > tolerance_s:
        return False
    expected = f"sha256={_digest(secret, timestamp, body)}"
    return hmac.compare_digest(expected, signature)
