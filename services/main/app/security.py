"""Password hashing, API-key minting, JWT issuing/verification."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from .config import settings

_hasher = PasswordHasher()

API_KEY_PREFIX = "tnk_"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def generate_api_key() -> tuple[str, str, str]:
    """Return `(full_key, prefix, key_hash)`. The full key is shown once."""

    body = secrets.token_urlsafe(32)
    full = f"{API_KEY_PREFIX}{body}"
    # The prefix is a lookup handle, so it must survive being stored in clear.
    prefix = full[: len(API_KEY_PREFIX) + 8]
    return full, prefix, hash_secret(full)


def hash_secret(value: str) -> str:
    """Fast, deterministic hash for high-entropy secrets (keys, session tokens).

    Argon2 is deliberately not used here: these values are random 256-bit
    strings, so there is nothing to brute-force, and every request would pay
    the KDF cost.
    """

    return hashlib.sha256(value.encode()).hexdigest()


def generate_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    return token, hash_secret(token)


def issue_jwt(subject: str, scopes: list[str], extra: dict | None = None) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_in = settings.jwt_ttl_seconds
    payload: dict = {
        "sub": subject,
        "scope": " ".join(scopes),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, expires_in


def decode_jwt(token: str) -> dict:
    """Verify a bearer token.

    Symmetric tokens are the ones this service issues itself; an asymmetric
    `jwt_public_key` lets an external issuer (an SSO provider, a campus
    gateway) mint tokens we only verify.
    """

    key = settings.jwt_public_key or settings.secret_key
    options = {"verify_aud": bool(settings.jwt_audience)}
    return jwt.decode(
        token,
        key,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options=options,
    )
