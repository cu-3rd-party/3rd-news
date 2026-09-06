from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import secrets
import socket
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import OKPKey
from lib.dto.principal import Principal
from lib.core.config import (
    AUTH_CSRF_COOKIE as CSRF_COOKIE,
    AUTH_DUMMY_PASSWORD_HASH as DUMMY_PASSWORD_HASH,
    AUTH_ROLE_SCOPES as ROLE_SCOPES,
    AUTH_SESSION_COOKIE as SESSION_COOKIE,
    AUTH_SESSION_TTL as SESSION_TTL,
    AUTH_TOKEN_TTL as TOKEN_TTL,
)
from lib.infra.storage.postgres.models import ApiKey, Session, User
from lib.interactor.errors.password_verification_capacity import (
    PasswordVerificationCapacityError,
)
from lib.interactor.interfaces.clients.authentication import AuthenticationClient
from sqlalchemy import or_, select, update

class AuthService(AuthenticationClient):
    API_PREFIX = "tn2_"

    def __init__(
        self,
        *,
        private_key: str,
        public_key: str,
        issuer: str = "thirdnews",
        audience: str = "thirdnews-api",
        password_verify_concurrency: int = 2,
        password_verify_queue_size: int = 16,
    ) -> None:
        self.private_key = OKPKey.import_key(private_key) if private_key else None
        self.public_key = OKPKey.import_key(public_key) if public_key else None
        self.issuer = issuer
        self.audience = audience
        self.passwords = PasswordHasher()
        self._password_verify_slots = asyncio.Semaphore(password_verify_concurrency)
        self._password_verify_capacity = password_verify_concurrency + password_verify_queue_size
        self._password_verifications_pending = 0
        self._rate_limit_key = hashlib.sha256(
            (private_key or public_key or issuer).encode()
        ).digest()
        self._session_factory = None
        self._api_key_touch_interval = timedelta(minutes=5)
        self._trusted_proxy_ips: frozenset[str] = frozenset()

    def bind_database(self, session_factory, *, api_key_touch_interval_seconds: int) -> None:
        self._session_factory = session_factory
        self._api_key_touch_interval = timedelta(seconds=api_key_touch_interval_seconds)

    def hash_password(self, password: str) -> str:
        return self.passwords.hash(password)

    def verify_password(self, password: str, encoded: str | None) -> bool:
        if not encoded:
            return False
        try:
            return self.passwords.verify(encoded, password)
        except VerifyMismatchError, InvalidHashError:
            return False

    async def verify_password_bounded(self, password: str, encoded: str | None) -> bool:
        if self._password_verifications_pending >= self._password_verify_capacity:
            raise PasswordVerificationCapacityError("password verification capacity exhausted")
        self._password_verifications_pending += 1
        try:
            async with self._password_verify_slots:
                worker = asyncio.create_task(
                    asyncio.to_thread(self.verify_password, password, encoded)
                )
                try:
                    return await asyncio.shield(worker)
                except asyncio.CancelledError:
                    while not worker.done():
                        try:
                            await asyncio.shield(worker)
                        except asyncio.CancelledError:
                            continue
                    if not worker.cancelled():
                        worker.exception()
                    raise
        finally:
            self._password_verifications_pending -= 1

    async def resolve_trusted_proxy_hosts(
        self, hosts: list[str], *, timeout_seconds: float = 3.0
    ) -> None:
        loop = asyncio.get_running_loop()
        addresses: set[str] = set()
        for host in hosts:
            try:
                literal = ipaddress.ip_address(host)
            except ValueError:
                try:
                    async with asyncio.timeout(timeout_seconds):
                        records = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
                except OSError, TimeoutError:
                    continue
                for _family, _kind, _protocol, _canonical, socket_address in records:
                    addresses.add(self._normalize_ip(str(socket_address[0])))
            else:
                addresses.add(self._normalize_ip(str(literal)))
        self._trusted_proxy_ips = frozenset(addresses)

    def client_ip(self, request) -> str | None:
        peer = request.client.host if request.client else None
        normalized_peer = self._normalize_ip(peer) if peer else None
        if normalized_peer in self._trusted_proxy_ips:
            forwarded = request.headers.get("x-forwarded-for", "").split(",", maxsplit=1)[0]
            if forwarded.strip():
                return self._normalize_ip(forwarded)
        return normalized_peer

    def rate_limit_identifiers(
        self, account: str, ip_address: str | None
    ) -> tuple[tuple[str, str], ...]:
        normalized_account = unicodedata.normalize("NFKC", account).strip().casefold()
        normalized_ip = self._normalize_ip(ip_address or "unknown")
        return (
            ("account", self._hash_rate_identifier("account", normalized_account)),
            ("ip", self._hash_rate_identifier("ip", normalized_ip)),
        )

    @staticmethod
    def _normalize_ip(ip_address: str) -> str:
        raw_ip = ip_address.strip().casefold()
        try:
            address = ipaddress.ip_address(raw_ip)
            mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
            return str(mapped or address)
        except ValueError:
            return raw_ip

    def _hash_rate_identifier(self, scope: str, value: str) -> str:
        return hmac.new(
            self._rate_limit_key,
            f"{scope}\0{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def hash_secret(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def generate_api_key(self) -> tuple[str, str, str]:
        secret = self.API_PREFIX + secrets.token_urlsafe(32)
        return secret, secret[:12], self.hash_secret(secret)

    def generate_session(self) -> tuple[str, str, str, str]:
        token = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        return token, self.hash_secret(token), csrf, self.hash_secret(csrf)

    def issue_token(self, principal: Principal) -> tuple[str, int]:
        if self.private_key is None:
            raise RuntimeError("auth private key is not configured")
        now = datetime.now(UTC)
        expires = now + TOKEN_TTL
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": principal.subject,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": str(uuid.uuid4()),
            "scope": " ".join(sorted(principal.scopes)),
            "name": principal.display_name,
            "role": principal.role,
            "user_id": str(principal.user_id) if principal.user_id else None,
        }
        return jwt.encode(
            {"alg": "Ed25519", "typ": "JWT"},
            claims,
            self.private_key,
            algorithms=["Ed25519"],
        ), int(TOKEN_TTL.total_seconds())

    def verify_token(self, token: str) -> Principal | None:
        if self.public_key is None:
            return None
        try:
            claims = jwt.decode(token, self.public_key, algorithms=["Ed25519"]).claims
        except JoseError:
            return None
        now = int(datetime.now(UTC).timestamp())
        audience = claims.get("aud")
        valid_audience = (
            audience == self.audience or isinstance(audience, list) and self.audience in audience
        )
        if claims.get("iss") != self.issuer or not valid_audience:
            return None
        if not isinstance(claims.get("exp"), int) or claims["exp"] <= now:
            return None
        if isinstance(claims.get("nbf"), int) and claims["nbf"] > now:
            return None
        scopes = claims.get("scope", "")
        return Principal(
            kind="jwt",
            subject=str(claims.get("sub", "")),
            display_name=str(claims.get("name") or claims.get("sub") or ""),
            scopes=frozenset(scopes.split() if isinstance(scopes, str) else scopes),
            user_id=uuid.UUID(claims["user_id"]) if claims.get("user_id") else None,
            role=claims.get("role"),
        )

    async def authenticate(self, request, session) -> Principal | None:
        authorization = request.headers.get("authorization", "")
        raw_key = request.headers.get("x-api-key")
        if not raw_key and authorization.lower().startswith("apikey "):
            raw_key = authorization[7:].strip()
        if raw_key:
            return await self._authenticate_api_key(raw_key, session)
        if authorization.lower().startswith("bearer "):
            principal = self.verify_token(authorization[7:].strip())
            if principal is None or principal.user_id is None:
                return None
            user = await session.get(User, principal.user_id)
            if user is None or not user.is_active:
                return None
            return Principal(
                "jwt",
                user.email,
                user.full_name or user.email,
                ROLE_SCOPES.get(user.role, frozenset({"read"})),
                user.id,
                role=user.role,
            )
        cookie = request.cookies.get(SESSION_COOKIE)
        if not cookie:
            return None
        row = (
            await session.execute(
                select(Session, User)
                .join(User)
                .where(Session.token_hash == self.hash_secret(cookie))
            )
        ).one_or_none()
        now = datetime.now(UTC)
        if (
            row is None
            or row.Session.revoked_at
            or row.Session.expires_at <= now
            or not row.User.is_active
        ):
            return None
        return Principal(
            "session",
            row.User.email,
            row.User.full_name or row.User.email,
            ROLE_SCOPES.get(row.User.role, frozenset({"read"})),
            row.User.id,
            role=row.User.role,
        )

    async def _authenticate_api_key(self, raw_key: str, fallback_session) -> Principal | None:
        session_factory = self._session_factory
        if session_factory is None:
            return await self._authenticate_api_key_in_session(
                raw_key, fallback_session, touch=False
            )
        async with session_factory() as session, session.begin():
            return await self._authenticate_api_key_in_session(raw_key, session, touch=True)

    async def _authenticate_api_key_in_session(
        self, raw_key: str, session, *, touch: bool
    ) -> Principal | None:
        key = (
            await session.execute(
                select(ApiKey).where(ApiKey.key_hash == self.hash_secret(raw_key))
            )
        ).scalar_one_or_none()
        moment = datetime.now(UTC)
        if (
            key is None
            or not key.enabled
            or key.revoked_at
            or key.expires_at
            and key.expires_at <= moment
        ):
            return None
        if touch:
            cutoff = moment - self._api_key_touch_interval
            await session.execute(
                update(ApiKey)
                .where(
                    ApiKey.id == key.id,
                    or_(ApiKey.last_used_at.is_(None), ApiKey.last_used_at < cutoff),
                )
                .values(last_used_at=moment)
            )
        return Principal(
            "api_key",
            str(key.id),
            key.name,
            frozenset(key.scopes),
            source_id=key.source_id,
            filter_preset=key.filter_preset,
        )

    @staticmethod
    def valid_csrf(request, session_row: Session) -> bool:
        header = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        return bool(
            header
            and cookie
            and hmac.compare_digest(header, cookie)
            and hmac.compare_digest(AuthService.hash_secret(header), session_row.csrf_hash)
        )
