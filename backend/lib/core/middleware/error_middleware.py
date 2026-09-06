import logging
from http import HTTPStatus
from typing import Final, cast

from fastapi.encoders import jsonable_encoder
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from lib.core.middleware.request_id_middleware import REQUEST_ID_HEADER, REQUEST_ID_STATE_KEY
from lib.core.responses import OrjsonResponse
from lib.interactor.errors.base import ServiceError

logger = logging.getLogger(__name__)

INTERNAL_ERROR_BODY: Final[dict[str, dict[str, str]]] = {
    "error": {"code": "SERVICE_ERROR", "message": "Произошла ошибка"},
}


def _request_id(scope: Scope) -> str | None:
    state = cast("dict[str, object] | None", scope.get("state"))
    if state is None:
        return None

    value = state.get(REQUEST_ID_STATE_KEY)
    if isinstance(value, str):
        return value
    return None


class ErrorHandlingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except ServiceError as exc:
            if response_started:
                raise
            await self._handle_service_error(exc, scope, receive, send)
        except Exception:
            if response_started:
                raise
            await self._handle_unexpected(scope, receive, send)

    async def _handle_service_error(
        self,
        exc: ServiceError,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        request = Request(scope)
        request_id = _request_id(scope)
        extra = cast("object", jsonable_encoder(exc.extra))
        content = cast("object", jsonable_encoder(exc.to_dict()))

        logger.warning(
            "ServiceError: %s %s -> %s (%s) extra=%r request_id=%s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.message,
            extra,
            request_id,
        )

        response = OrjsonResponse(
            content=content,
            status_code=exc.status_code,
            headers={REQUEST_ID_HEADER: request_id} if request_id else None,
        )
        await response(scope, receive, send)

    async def _handle_unexpected(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        request = Request(scope)
        request_id = _request_id(scope)

        logger.exception(
            "Unexpected error %s %s request_id=%s",
            request.method,
            request.url.path,
            request_id,
        )

        response = OrjsonResponse(
            content=INTERNAL_ERROR_BODY,
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            headers={REQUEST_ID_HEADER: request_id} if request_id else None,
        )
        await response(scope, receive, send)
