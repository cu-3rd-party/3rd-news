import json
import subprocess
from pathlib import Path
from typing import Any

import aiohttp
from pydantic import SecretStr

from tools.ops.load_settings import LoadSettings

ROOT = Path(__file__).resolve().parents[2]


def compose_bootstrap_password() -> str:
    completed = subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "thirdnews-bootstrap-password"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    password = completed.stdout.strip()
    if not password:
        raise RuntimeError("bootstrap password command returned no value")
    return password


async def json_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    expected: set[int],
    **kwargs: Any,
) -> tuple[int, dict[str, Any]]:
    async with session.request(method, url, **kwargs) as response:
        body = await response.read()
        if response.status not in expected:
            detail = body.decode(errors="replace")[:500]
            raise RuntimeError(f"{method} {url} returned {response.status}: {detail}")
        if not body:
            return response.status, {}
        value = json.loads(body)
        if not isinstance(value, dict):
            raise TypeError(f"{method} {url} returned a non-object JSON body")
        return response.status, value


async def authenticate(session: aiohttp.ClientSession, settings: LoadSettings) -> str:
    if settings.token_value:
        return settings.token_value
    if not settings.password_value:
        settings.admin_password = SecretStr(compose_bootstrap_password())
    password = settings.password_value
    _, payload = await json_request(
        session,
        "POST",
        f"{settings.base_url}/api/v1/auth/token",
        expected={200},
        json={"email": settings.email_value, "password": password},
    )
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("token endpoint did not return access_token")
    return token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
