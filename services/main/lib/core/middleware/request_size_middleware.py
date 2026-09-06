from __future__ import annotations

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestSizeMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                declared_size = int(declared)
            except ValueError:
                await self._reject(scope, receive, send, 400, "invalid Content-Length")
                return
            if declared_size < 0:
                await self._reject(scope, receive, send, 400, "invalid Content-Length")
                return
            if declared_size > self.max_bytes:
                await self._reject(scope, receive, send, 413, "request body is too large")
                return

        received = 0

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise OverflowError("request body is too large")
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except OverflowError:
            await self._reject(scope, receive, send, 413, "request body is too large")

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        message: str,
    ) -> None:
        response = JSONResponse({"detail": message}, status_code=status_code)
        await response(scope, receive, send)
