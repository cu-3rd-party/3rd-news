import logging
import re
import uuid
from typing import Final, cast

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER: Final = "X-Request-ID"
REQUEST_ID_STATE_KEY: Final = "request_id"
REQUEST_ID_HEADER_BYTES: Final = REQUEST_ID_HEADER.lower().encode("latin-1")
REQUEST_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get(REQUEST_ID_HEADER)
        if request_id is None:
            request_id = str(uuid.uuid4())
        else:
            request_id = request_id.strip()
            if REQUEST_ID_PATTERN.fullmatch(request_id) is None:
                logger.warning("Invalid X-Request-ID header was ignored")
                request_id = str(uuid.uuid4())

        state = scope.get("state")
        if not isinstance(state, dict):
            state = {}
            scope["state"] = state
        state[REQUEST_ID_STATE_KEY] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = cast("list[tuple[bytes, bytes]]", message.get("headers", []))
                headers = [
                    header for header in raw_headers if header[0].lower() != REQUEST_ID_HEADER_BYTES
                ]
                headers.append((REQUEST_ID_HEADER_BYTES, request_id.encode("latin-1")))
                message = {**message, "headers": headers}

            await send(message)

        await self.app(scope, receive, send_with_request_id)
