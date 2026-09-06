import uuid
from typing import Any

import aiohttp

from tools.ops.load_http import bearer, json_request
from tools.ops.load_settings import LoadSettings


async def negative_auth_checks(
    session: aiohttp.ClientSession,
    settings: LoadSettings,
    admin_headers: dict[str, str],
    source: dict[str, Any],
) -> dict[str, str]:
    probe = {
        "source": source["slug"],
        "external_id": f"negative:{settings.run_id}",
        "body_md": "must not be accepted",
    }
    status, _ = await json_request(
        session,
        "POST",
        f"{settings.base_url}/api/v1/news",
        expected={401},
        json=probe,
    )
    results = {"unauthenticated_ingest": f"passed:{status}"}
    _, created = await json_request(
        session,
        "POST",
        f"{settings.base_url}/api/v1/admin/api-keys",
        expected={201},
        headers=admin_headers,
        json={
            "name": f"revoked-load-probe-{settings.run_id}",
            "scopes": ["ingest"],
            "source_id": source["id"],
        },
    )
    key = created.get("key")
    secret = created.get("secret")
    if (
        not isinstance(key, dict)
        or not isinstance(key.get("id"), str)
        or not isinstance(secret, str)
    ):
        raise TypeError("API-key creation returned an invalid body")
    await json_request(
        session,
        "POST",
        f"{settings.base_url}/api/v1/admin/api-keys/{key['id']}/revoke",
        expected={200},
        headers=admin_headers,
    )
    status, _ = await json_request(
        session,
        "POST",
        f"{settings.base_url}/api/v1/news",
        expected={401},
        headers=bearer(secret),
        json=probe,
    )
    results["revoked_api_key"] = f"passed:{status}"
    if not settings.email_value or not settings.password_value:
        results["cookie_csrf"] = "skipped:no-admin-credentials"
        return results
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(
        timeout=session.timeout,
        cookie_jar=cookie_jar,
    ) as cookie_session:
        await json_request(
            cookie_session,
            "POST",
            f"{settings.base_url}/api/v1/auth/login",
            expected={200},
            json={"email": settings.email_value, "password": settings.password_value},
        )
        status, _ = await json_request(
            cookie_session,
            "POST",
            f"{settings.base_url}/api/v1/admin/sources",
            expected={403},
            json={
                "slug": f"csrf-must-fail-{uuid.uuid4().hex[:12]}",
                "title": "CSRF rejection probe",
            },
        )
        results["cookie_csrf"] = f"passed:{status}"
    return results
