import time

from joserfc import jwt

from ...dto.signed_message_claims import SignedMessageClaims
from ..errors.claim_mismatch import ClaimMismatchError
from ..errors.expired_signature import ExpiredSignatureError
from ..errors.replay import ReplayError
from ..errors.signature import SignatureError
from ..interfaces.storage.replay_guard import ReplayGuard
from .sign_message import ALGORITHM, DEFAULT_TTL_S, KeyInput, body_digest, key_from_input


def verify_message(
    public_key: KeyInput,
    token: str,
    body: bytes,
    *,
    issuer: str,
    audience: str,
    job_id: str,
    attempt_id: str,
    node_id: str,
    replay_guard: ReplayGuard | None = None,
    now: int | None = None,
    clock_skew_s: int = 30,
) -> SignedMessageClaims:
    try:
        decoded = jwt.decode(token, key_from_input(public_key), algorithms=[ALGORITHM])
        header = dict(decoded.header)
        claims = dict(decoded.claims)
    except Exception as exc:
        raise SignatureError("invalid signature") from exc
    if header.get("alg") != ALGORITHM:
        raise SignatureError("unexpected signing algorithm")
    required = {
        "iss",
        "aud",
        "iat",
        "exp",
        "jti",
        "job_id",
        "attempt_id",
        "node_id",
        "body_sha256",
    }
    if not required.issubset(claims):
        raise SignatureError("required claims are missing")
    current = int(time.time()) if now is None else now
    try:
        issued_at = int(claims["iat"])
        expires_at = int(claims["exp"])
    except (TypeError, ValueError) as exc:
        raise SignatureError("invalid time claims") from exc
    if issued_at > current + clock_skew_s or expires_at < current - clock_skew_s:
        raise ExpiredSignatureError("token is outside its validity window")
    if expires_at <= issued_at or expires_at - issued_at > DEFAULT_TTL_S:
        raise SignatureError("invalid token lifetime")
    expected = {
        "iss": issuer,
        "aud": audience,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "node_id": node_id,
        "body_sha256": body_digest(body),
    }
    for claim, value in expected.items():
        if claims.get(claim) != value:
            raise ClaimMismatchError(f"claim {claim} does not match")
    token_id = str(claims["jti"])
    if replay_guard is not None and not replay_guard(token_id, expires_at):
        raise ReplayError("token was already used")
    return SignedMessageClaims(
        issuer=issuer,
        audience=audience,
        issued_at=issued_at,
        expires_at=expires_at,
        token_id=token_id,
        job_id=job_id,
        attempt_id=attempt_id,
        node_id=node_id,
        body_sha256=str(claims["body_sha256"]),
    )
