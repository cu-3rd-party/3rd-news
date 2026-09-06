from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ...interactor.use_cases.management_auth import management_auth_status
from ..config import Settings


class ManagementAuthMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._token = settings.parser_api_token.get_secret_value()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization")
        denial = management_auth_status(
            str(scope.get("path", "")),
            authorization.decode(errors="ignore") if authorization else None,
            self._token,
        )
        if denial == 503:
            await JSONResponse({"detail": "management API is disabled"}, 503)(scope, receive, send)
            return
        if denial == 401:
            await JSONResponse({"detail": "authorization required"}, 401)(scope, receive, send)
            return
        await self.app(scope, receive, send)
