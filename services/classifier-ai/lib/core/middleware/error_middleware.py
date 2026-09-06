from starlette.types import ASGIApp, Receive, Scope, Send

from ..responses import internal_error


class ErrorHandlingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await self.app(scope, receive, send)
        except Exception:
            if scope["type"] != "http":
                raise
            headers = dict(scope.get("headers", []))
            request_id = headers.get(b"x-request-id", b"").decode(errors="ignore")
            await internal_error(request_id)(scope, receive, send)
