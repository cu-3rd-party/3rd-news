from __future__ import annotations

import logging
import uuid
from typing import cast

from lib.core.middleware.error_middleware import ErrorHandlingMiddleware
from starlette.types import Message, Scope


async def test_unhandled_exception_log_never_contains_exception_secret(caplog) -> None:
    marker = f"private-news-{uuid.uuid4().hex}"

    async def failing_app(_scope, _receive, _send) -> None:
        raise RuntimeError(marker)

    async def receive() -> dict:
        return {"type": "http.disconnect"}

    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/news",
        "raw_path": b"/api/v1/news",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
        "state": {"request_id": "qa-request"},
    }
    caplog.set_level(logging.ERROR)
    await ErrorHandlingMiddleware(failing_app)(cast(Scope, scope), receive, send)
    assert marker not in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert any(message["type"] == "http.response.start" for message in messages)
