import base64
from urllib.parse import urlsplit

import pytest
from lib.core.config import Settings
from pydantic import ValidationError

KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:8081",
        "https://127.0.0.1",
        "https://10.0.0.1",
        "https://localhost",
        "https://user:secret@uploads.example.edu",
    ],
)
def test_production_rejects_unsafe_upload_origins(endpoint):
    parsed = urlsplit(endpoint)
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            raw_audit_encryption_key=KEY,
            file_public_scheme=parsed.scheme,
            file_public_host=parsed.netloc if parsed.username else parsed.hostname or "",
            file_public_port=parsed.port or 443,
        )


@pytest.mark.parametrize("key", ["", "secret", base64.urlsafe_b64encode(b"x" * 32).decode()])
def test_production_requires_protected_raw_audit(key):
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            file_public_scheme="https",
            file_public_host="uploads.example.edu",
            file_public_port=443,
            raw_audit_encryption_key=key,
        )


def test_production_accepts_public_origin_and_generated_key():
    settings = Settings(
        environment="production",
        file_public_scheme="https",
        file_public_host="uploads.example.edu",
        file_public_port=443,
        raw_audit_encryption_key=KEY,
    )
    assert settings.file_public_endpoint == "https://uploads.example.edu:443"


@pytest.mark.parametrize("environment", ["Production", "prod", "staging", "test"])
def test_unknown_environment_cannot_bypass_production_boundaries(environment):
    with pytest.raises(ValidationError):
        Settings(environment=environment)
