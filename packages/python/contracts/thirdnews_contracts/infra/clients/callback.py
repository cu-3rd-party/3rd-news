import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime

import aiohttp

from ...dto.classify_request import ClassifyRequest
from ...dto.classify_response import ClassifyResponse
from ...interactor.errors.signature import SignatureError
from ...interactor.interfaces.clients.callback import CallbackGateway
from ...interactor.use_cases.sign_message import KeyInput, authorization_header, sign_message


class CallbackClient(CallbackGateway):
    def __init__(self, private_key: KeyInput, signing_issuer: str, node_id: str) -> None:
        self._private_key = private_key
        self._signing_issuer = signing_issuer
        self._node_id = node_id

    async def deliver(
        self,
        request: ClassifyRequest,
        awaitable: Awaitable[ClassifyResponse],
    ) -> None:
        callback = request.options.callback
        if callback is None:
            return
        try:
            remaining = (callback.deadline_at - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                return
            result = await asyncio.wait_for(awaitable, timeout=remaining)
            if not isinstance(result, ClassifyResponse):
                return
            body = result.model_dump_json(exclude_none=True).encode()
            token = sign_message(
                self._private_key,
                body,
                issuer=self._signing_issuer,
                audience=callback.audience,
                job_id=request.job_id,
                attempt_id=request.attempt_id,
                node_id=self._node_id,
                ttl_s=max(1, min(300, int(remaining))),
            )
            timeout = aiohttp.ClientTimeout(total=max(1, min(remaining, 30)))
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(
                    str(callback.url),
                    data=body,
                    headers={
                        **authorization_header(token),
                        "Content-Type": "application/json",
                    },
                ) as response,
            ):
                await response.read()
        except TimeoutError, aiohttp.ClientError, SignatureError:
            return
        except Exception:
            return
