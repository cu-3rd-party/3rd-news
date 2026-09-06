from __future__ import annotations

import asyncio
import json
import socket
import uuid

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from lib.core.config import Settings
from thirdnews_contracts import (
    AttachmentInput,
    AttachmentKind,
    IngestClient,
    IngestError,
    IngestStatus,
    NewsSubmission,
)
from yarl import URL

API_BASE = "http://api:8000"


class ComposeUploadResolver(AbstractResolver):
    def __init__(self) -> None:
        self.delegate = aiohttp.ThreadedResolver()

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        target = "proxy" if host in {"localhost", "127.0.0.1"} and port == 8081 else host
        resolved = await self.delegate.resolve(target, port, family)
        return [ResolveResult(**{**item, "hostname": host}) for item in resolved]

    async def close(self) -> None:
        await self.delegate.close()


async def main() -> None:
    settings = Settings()
    run = uuid.uuid4().hex
    key_id: str | None = None
    revoked = False
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as admin:

        async def call(
            method: str,
            path: str,
            *,
            status: int = 200,
            payload: object | None = None,
        ) -> object:
            headers: dict[str, str] = {}
            csrf = admin.cookie_jar.filter_cookies(URL(API_BASE)).get("thirdnews_csrf")
            if csrf is not None:
                headers["X-CSRF-Token"] = csrf.value
            async with admin.request(
                method,
                f"{API_BASE}{path}",
                json=payload,
                headers=headers,
            ) as response:
                raw = await response.read()
                assert response.status == status, (
                    method,
                    path,
                    response.status,
                    response.headers.get("X-Request-ID"),
                )
                return json.loads(raw) if raw else {}

        await call(
            "POST",
            "/api/v1/auth/login",
            payload={
                "email": settings.bootstrap_admin_email,
                "password": settings.bootstrap_admin_password,
            },
        )
        created = await call(
            "POST",
            "/api/v1/admin/api-keys",
            status=201,
            payload={"name": f"live-ingest-client-{run[:12]}", "scopes": ["ingest"]},
        )
        assert isinstance(created, dict)
        key = created["key"]
        secret = created["secret"]
        assert isinstance(key, dict) and isinstance(secret, str)
        key_id = str(key["id"])

        resolver = ComposeUploadResolver()
        connector = aiohttp.TCPConnector(resolver=resolver)
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as ingest_session:
                client = IngestClient(API_BASE, secret, timeout=60, session=ingest_session)
                content = b"Synthetic shared ingest client upload.\n"
                upload = await client.upload("sdk-smoke.txt", "text/plain", content)
                result = await client.submit(
                    NewsSubmission(
                        idempotency_key=f"live-ingest-client-{run}",
                        title="Synthetic shared IngestClient smoke",
                        body_md="Synthetic data used only in the isolated Compose test database.",
                        attachments=[
                            AttachmentInput(
                                kind=AttachmentKind.FILE,
                                upload_intent_id=upload.upload_id,
                                filename="sdk-smoke.txt",
                                mime="text/plain",
                            )
                        ],
                    )
                )
                assert result.status is IngestStatus.ACCEPTED

                await call("POST", f"/api/v1/admin/api-keys/{key_id}/revoke")
                revoked = True
                try:
                    await client.submit(
                        NewsSubmission(
                            idempotency_key=f"live-ingest-client-revoked-{run}",
                            body_md="Synthetic revoked-key check.",
                        )
                    )
                except IngestError as error:
                    assert error.status_code == 401
                else:
                    raise AssertionError("revoked ingest API key was accepted")
        finally:
            await resolver.close()
            if key_id is not None and not revoked:
                await call("POST", f"/api/v1/admin/api-keys/{key_id}/revoke")

    print(
        json.dumps(
            {
                "api_key_header": "X-API-Key",
                "submit": "accepted",
                "upload": "completed-and-attached",
                "revoked_key": "denied",
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
