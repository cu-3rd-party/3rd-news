from __future__ import annotations

import json

from lib.dto.classifier_dispatch import ClassifierDispatch
from lib.interactor.errors.classifier_protocol import ClassifierProtocolError
from lib.interactor.interfaces.clients.classifier import ClassifierGateway
from lib.interactor.interfaces.clients.http import HttpClient
from pydantic import ValidationError
from thirdnews_contracts import (
    ClassifyRequest,
    ClassifyResponse,
    authorization_header,
    sign_message,
)


class ClassifierClient(ClassifierGateway):
    def __init__(
        self,
        *,
        private_key: str,
        issuer: str,
        audience: str,
        node_id: str,
        url_validator: HttpClient,
        timeout_seconds: float = 30.0,
        response_max_bytes: int = 1_000_000,
    ) -> None:
        self._private_key = private_key
        self._issuer = issuer
        self._audience = audience
        self._node_id = node_id
        self._validator = url_validator
        self._timeout_seconds = timeout_seconds
        self._response_max_bytes = response_max_bytes

    async def classify(
        self,
        endpoint: str,
        request: ClassifyRequest,
        *,
        target_node_id: str | None = None,
    ) -> ClassifierDispatch:
        url = f"{endpoint.rstrip('/')}/classify"
        await self._validator.validate_url(url)
        body = request.model_dump_json(exclude_none=True).encode("utf-8")
        token = sign_message(
            self._private_key,
            body,
            issuer=self._issuer,
            audience=self._audience,
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            node_id=target_node_id or self._node_id,
            ttl_s=min(300, max(1, int(self._timeout_seconds))),
        )
        headers = {"Content-Type": "application/json", **authorization_header(token)}
        result = await self._validator.post_bytes(
            url,
            body,
            headers=headers,
            max_bytes=self._response_max_bytes,
        )
        raw = result.body
        if result.status == 202:
            return ClassifierDispatch(True, None, raw, result.status)
        if result.status >= 400:
            raise ClassifierProtocolError(f"classifier returned HTTP {result.status}", raw_body=raw)
        try:
            parsed = ClassifyResponse.model_validate(json.loads(raw))
        except (ValueError, ValidationError) as exc:
            raise ClassifierProtocolError(
                "classifier returned an invalid v2 body", raw_body=raw
            ) from exc
        expected = (
            request.request_id,
            request.job_id,
            request.attempt_id,
            request.news.id,
            request.news.version,
        )
        actual = (
            parsed.request_id,
            parsed.job_id,
            parsed.attempt_id,
            parsed.news_id,
            parsed.news_version,
        )
        if actual != expected:
            raise ClassifierProtocolError(
                "classifier response does not belong to this attempt", raw_body=raw
            )
        return ClassifierDispatch(False, parsed, raw, result.status)
