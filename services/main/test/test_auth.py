from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lib.infra.clients.auth import AuthService, Principal
from lib.interactor.errors.password_verification_capacity import (
    PasswordVerificationCapacityError,
)


def auth_service() -> AuthService:
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return AuthService(private_key=private_pem, public_key=public_pem)


def test_password_hash_is_salted_and_verifiable() -> None:
    auth = auth_service()
    first = auth.hash_password("correct horse battery staple")
    second = auth.hash_password("correct horse battery staple")
    assert first != second
    assert auth.verify_password("correct horse battery staple", first)
    assert not auth.verify_password("wrong", first)


def test_ed25519_token_round_trip_and_tamper_rejection() -> None:
    auth = auth_service()
    principal = Principal("user", "editor@example.edu", "Editor", frozenset({"read", "editor"}))
    token, expires = auth.issue_token(principal)
    verified = auth.verify_token(token)
    assert expires == 900
    assert verified is not None
    assert verified.subject == principal.subject
    assert verified.scopes == principal.scopes
    assert auth.verify_token(token[:-1] + ("A" if token[-1] != "A" else "B")) is None


def test_api_keys_store_only_hash() -> None:
    auth = auth_service()
    secret, prefix, digest = auth.generate_api_key()
    assert secret.startswith("tn2_")
    assert prefix == secret[:12]
    assert secret not in digest
    assert digest == auth.hash_secret(secret)


def test_rate_limit_identifiers_normalize_account_without_storing_it() -> None:
    auth = auth_service()
    first = auth.rate_limit_identifiers("  Editor@Example.EDU ", "2001:0db8:0:0:0:0:0:1")
    second = auth.rate_limit_identifiers("editor@example.edu", "2001:db8::1")
    assert first == second
    assert "editor@example.edu" not in repr(first)


@pytest.mark.asyncio
async def test_password_verification_is_threaded_and_concurrency_bounded(monkeypatch) -> None:
    auth = AuthService(private_key="", public_key="", password_verify_concurrency=2)
    lock = threading.Lock()
    running = 0
    maximum = 0

    def slow_verify(_password: str, _encoded: str | None) -> bool:
        nonlocal running, maximum
        with lock:
            running += 1
            maximum = max(maximum, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return False

    monkeypatch.setattr(auth, "verify_password", slow_verify)
    tasks = [auth.verify_password_bounded("wrong", "hash") for _ in range(6)]
    ticker = asyncio.create_task(asyncio.sleep(0.01))
    results = await asyncio.gather(*tasks)
    assert ticker.done()
    assert results == [False] * 6
    assert maximum == 2


@pytest.mark.asyncio
async def test_cancelled_password_verification_holds_its_capacity_slot(monkeypatch) -> None:
    auth = AuthService(private_key="", public_key="", password_verify_concurrency=1)
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    running = 0
    maximum = 0

    def controlled_verify(_password: str, _encoded: str | None) -> bool:
        nonlocal running, maximum
        with lock:
            running += 1
            maximum = max(maximum, running)
        started.set()
        release.wait(timeout=2)
        with lock:
            running -= 1
        return False

    monkeypatch.setattr(auth, "verify_password", controlled_verify)
    first = asyncio.create_task(auth.verify_password_bounded("first", "hash"))
    assert await asyncio.to_thread(started.wait, 1)
    first.cancel()
    second = asyncio.create_task(auth.verify_password_bounded("second", "hash"))
    await asyncio.sleep(0.02)
    assert maximum == 1
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert await second is False
    assert maximum == 1


@pytest.mark.asyncio
async def test_password_verification_queue_has_a_hard_capacity(monkeypatch) -> None:
    auth = AuthService(
        private_key="",
        public_key="",
        password_verify_concurrency=1,
        password_verify_queue_size=0,
    )
    started = threading.Event()
    release = threading.Event()

    def controlled_verify(_password: str, _encoded: str | None) -> bool:
        started.set()
        release.wait(timeout=2)
        return False

    monkeypatch.setattr(auth, "verify_password", controlled_verify)
    first = asyncio.create_task(auth.verify_password_bounded("first", "hash"))
    assert await asyncio.to_thread(started.wait, 1)
    with pytest.raises(PasswordVerificationCapacityError):
        await auth.verify_password_bounded("second", "hash")
    release.set()
    assert await first is False


@pytest.mark.asyncio
async def test_forwarded_ip_is_used_only_for_an_exact_trusted_proxy() -> None:
    auth = AuthService(private_key="", public_key="")
    forged = SimpleNamespace(
        client=SimpleNamespace(host="198.51.100.10"),
        headers={"x-forwarded-for": "203.0.113.99"},
    )
    assert auth.client_ip(forged) == "198.51.100.10"

    await auth.resolve_trusted_proxy_hosts(["198.51.100.10"])
    assert auth.client_ip(forged) == "203.0.113.99"
