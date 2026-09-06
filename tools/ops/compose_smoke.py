import asyncio
import hashlib
import json
import time
import uuid
from typing import Any

import aiohttp
from yarl import URL

from tools.ops.compose_settings import ComposeSettings
from tools.ops.load_http import compose_bootstrap_password


async def main() -> None:
    settings = ComposeSettings()
    base = settings.base_url
    password = settings.password_value or compose_bootstrap_password()
    run = uuid.uuid4().hex[:12]
    checks: list[str] = []
    started = time.monotonic()
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as client:

        async def call(
            method: str,
            path: str,
            *,
            status: int = 200,
            payload: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            request_headers = dict(headers or {})
            csrf = client.cookie_jar.filter_cookies(URL(base)).get("thirdnews_csrf")
            if csrf:
                request_headers["x-csrf-token"] = csrf.value
            async with client.request(
                method, base + path, json=payload, headers=request_headers
            ) as response:
                body = await response.read()
                assert response.status == status, (
                    method,
                    path,
                    response.status,
                    status,
                    response.headers.get("x-request-id"),
                )
                if not body:
                    return {}
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise TypeError(f"{method} {path} returned a non-object JSON body")
                return value

        await call("GET", "/api/v1/feed", status=401)
        checks.append("anonymous feed denied")
        await call(
            "POST",
            "/api/v1/auth/login",
            payload={
                "email": settings.admin_email,
                "password": password,
            },
        )
        await call("GET", "/api/v1/admin/stats")
        await call("PUT", "/api/v1/admin/settings/auto-publish", payload={"enabled": True})
        checks.append("login and admin stats")
        classifiers = await call("GET", "/api/v1/admin/classifiers")
        for classifier in classifiers["items"]:
            if URL(classifier["endpoint"]).host == "classifier-ai":
                updated = await call(
                    "PATCH",
                    f"/api/v1/admin/classifiers/{classifier['id']}",
                    payload={"timeout_seconds": 180},
                )
                assert updated["has_signing_key"]
        facets = await call("GET", "/api/v1/admin/facets")
        if not facets["items"]:
            facet = await call(
                "POST",
                "/api/v1/admin/facets",
                status=201,
                payload={"slug": "smoke_topic", "title": "Topic", "kind": "single"},
            )
            await call(
                "POST",
                f"/api/v1/admin/facets/{facet['id']}/values",
                status=201,
                payload={"slug": "university", "title": "University news"},
            )
        checks.append("nonempty taxonomy and signed AI node registration")
        source = await call(
            "POST",
            "/api/v1/admin/sources",
            status=201,
            payload={
                "slug": f"smoke-{run}",
                "title": "Synthetic smoke source",
                "skip_classification": False,
            },
        )
        data = b"Synthetic attachment for private media checks.\n"
        intent = await call(
            "POST",
            "/api/v1/uploads/presign",
            status=201,
            payload={
                "filename": "smoke.txt",
                "content_type": "text/plain",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
        upload_url = URL(intent["url"])
        headers = {**intent["headers"], "Host": upload_url.raw_authority}
        async with client.put(upload_url, data=data, headers=headers) as response:
            await response.read()
            assert response.status == 200, ("presigned PUT", response.status)
        await call(
            "POST",
            "/api/v1/uploads/complete",
            payload={"upload_id": intent["upload_id"]},
        )
        async with client.put(upload_url, data=b"X" * len(data), headers=headers) as response:
            await response.read()
            assert response.status in (200, 400, 403), ("repeat PUT", response.status)
        checks.append("Garage presign, complete and immutable promotion")
        payload = {
            "source": source["slug"],
            "external_id": run,
            "title": f"Smoke {run}",
            "body_md": "Synthetic university news for smoke validation.",
            "attachments": [{"upload_intent_id": intent["upload_id"], "filename": "smoke.txt"}],
        }
        accepted = await call("POST", "/api/v1/news", status=202, payload=payload)
        duplicate = await call("POST", "/api/v1/news", status=202, payload=payload)
        assert accepted["submission_id"] == duplicate["submission_id"]
        await call("POST", "/api/v1/news", status=409, payload={**payload, "title": "Changed"})
        checks.append("idempotent replay and conflicting payload")
        batch = await call(
            "POST", "/api/v1/news/batch", status=202, payload={"items": [payload, {}]}
        )
        assert [item["status"] for item in batch["results"]] == [
            "duplicate",
            "rejected",
        ]
        checks.append("batch item isolation")
        submission = await call("GET", f"/api/v1/submissions/{accepted['submission_id']}")
        news_id = submission["news_id"]
        assert news_id
        deadline = time.monotonic() + 240
        while True:
            detail = await call("GET", f"/api/v1/admin/news/{news_id}")
            assert detail["id"] == news_id
            if detail["status"] in ("published", "needs_review", "rejected"):
                break
            assert time.monotonic() < deadline, ("pipeline deadline", detail["status"])
            await asyncio.sleep(1)
        assert detail["status"] == "published", ("pipeline result", detail["status"])
        checks.append("outbox, broker and pipeline publication")
        deadline = time.monotonic() + 60
        while True:
            async with client.get(base + "/api/v1/feed", params={"q": run}) as response:
                feed = await response.json()
                if response.status == 200 and any(item["id"] == news_id for item in feed["items"]):
                    break
                assert response.status in (200, 503), ("feed", response.status)
            assert time.monotonic() < deadline, "search projection deadline"
            await asyncio.sleep(1)
        checks.append("Meilisearch confirmed projection")
        media = detail["attachments"][0]["id"]
        async with client.get(base + f"/api/v1/media/{media}") as response:
            assert response.status == 200
            assert await response.read() == data
        async with client.get(
            base + f"/api/v1/media/{media}", headers={"Range": "bytes=0-8"}
        ) as response:
            assert response.status == 206
            assert await response.read() == data[:9]
        async with client.head(base + f"/api/v1/media/{media}") as response:
            assert response.status == 200
        checks.append("authorized media GET, HEAD and Range")
        async with aiohttp.ClientSession() as anonymous:
            for path in (
                f"/api/v1/news/{news_id}",
                f"/api/v1/media/{media}",
                "/api/v1/rss.xml",
            ):
                async with anonymous.get(base + path) as response:
                    await response.read()
                    assert response.status == 401, (
                        "anonymous access",
                        path,
                        response.status,
                    )
        checks.append("anonymous detail, media and RSS denied")
        await call("POST", "/api/v1/auth/logout", status=204)
        await call("GET", "/api/v1/feed", status=401)
        checks.append("session revoked")
    print(
        json.dumps(
            {
                "run": run,
                "checks": checks,
                "seconds": round(time.monotonic() - started, 2),
            }
        )
    )


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
