import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode(errors="ignore") or str(uuid.uuid4())

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                mutable = list(message.get("headers", []))
                mutable.append((b"x-request-id", request_id.encode()))
                message["headers"] = mutable
            await send(message)

        await self.app(scope, receive, send_with_id)
