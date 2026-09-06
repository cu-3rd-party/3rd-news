from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class RawPayloadProtector:
    _AAD = b"thirdnews-ai-audit-v2"

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("raw audit encryption key is required")
        try:
            decoded = base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4))
        except ValueError:
            decoded = b""
        key_material = decoded if len(decoded) >= 32 else secret.encode("utf-8")
        self._cipher = AESGCM(hashlib.sha256(key_material).digest())

    def encrypt(self, value: bytes) -> bytes:
        nonce = os.urandom(12)
        return b"\x01" + nonce + self._cipher.encrypt(nonce, value, self._AAD)

    def decrypt(self, value: bytes) -> bytes:
        if len(value) < 14 or value[0] != 1:
            raise ValueError("unsupported encrypted payload")
        return self._cipher.decrypt(value[1:13], value[13:], self._AAD)
