from __future__ import annotations

import logging

from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from lib.interactor.errors import BaseInteractorError

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def wrapped(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        except BaseInteractorError as error:
            if response_started:
                raise
            response = JSONResponse(
                {"error": {"code": error.code, "message": error.message}},
                status_code=error.status_code,
            )
            await response(scope, receive, send)
        except Exception as error:
            if response_started:
                raise
            request = Request(scope)
            request_id = scope.get("state", {}).get("request_id")
            logger.error(
                "Unhandled request error method=%s path=%s request_id=%s error_type=%s",
                request.method,
                request.url.path,
                request_id,
                type(error).__name__,
            )
            response = JSONResponse(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Internal server error",
                        "request_id": request_id,
                    }
                },
                status_code=500,
            )
            await response(scope, receive, send)
