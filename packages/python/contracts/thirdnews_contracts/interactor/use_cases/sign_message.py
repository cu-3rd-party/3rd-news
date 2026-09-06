import hashlib
import time
import uuid
from typing import Any

from joserfc import jwt
from joserfc.jwk import OKPKey

from ..errors.signature import SignatureError

ALGORITHM = "Ed25519"
AUTHORIZATION_HEADER = "Authorization"
DEFAULT_TTL_S = 300
type KeyInput = str | bytes | dict[str, Any] | OKPKey


def key_from_input(value: KeyInput) -> OKPKey:
    key = value if isinstance(value, OKPKey) else OKPKey.import_key(value)
    if key.get("crv") != "Ed25519":
        raise SignatureError("only Ed25519 keys are accepted")
    return key


def body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sign_message(
    private_key: KeyInput,
    body: bytes,
    *,
    issuer: str,
    audience: str,
    job_id: str,
    attempt_id: str,
    node_id: str,
    ttl_s: int = DEFAULT_TTL_S,
    now: int | None = None,
    token_id: str | None = None,
) -> str:
    if ttl_s <= 0 or ttl_s > DEFAULT_TTL_S:
        raise ValueError(f"ttl_s must be between 1 and {DEFAULT_TTL_S}")
    issued_at = int(time.time()) if now is None else now
    claims = {
        "iss": issuer,
        "aud": audience,
        "iat": issued_at,
        "exp": issued_at + ttl_s,
        "jti": token_id or str(uuid.uuid4()),
        "job_id": job_id,
        "attempt_id": attempt_id,
        "node_id": node_id,
        "body_sha256": body_digest(body),
    }
    return jwt.encode(
        {"alg": ALGORITHM, "typ": "JWT"},
        claims,
        key_from_input(private_key),
        algorithms=[ALGORITHM],
    )


def authorization_header(token: str) -> dict[str, str]:
    return {AUTHORIZATION_HEADER: f"Bearer {token}"}


def bearer_token(value: str | None) -> str:
    if value is None:
        raise SignatureError("missing Authorization header")
    scheme, separator, token = value.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise SignatureError("expected Bearer token")
    return token
