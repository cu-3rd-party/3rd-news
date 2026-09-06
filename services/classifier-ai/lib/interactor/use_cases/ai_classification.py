import time
from typing import Any

from thirdnews_contracts import (
    AITrace,
    ClassificationError,
    ClassificationStatus,
    ClassifyRequest,
    ClassifyResponse,
)

from ...core.config import Settings
from ...domain.entities.classifier import IDENTITY
from ...domain.entities.response_schema import PROMPT_VERSION, SCHEMA_VERSION
from ..interfaces.clients.provider import ProviderClient
from .build_payload import build_payload
from .normalize_response import content, labels
from .trace_parameters import trace_parameters


class AIClassification:
    def __init__(self, settings: Settings, provider: ProviderClient) -> None:
        self._settings = settings
        self._provider = provider

    async def execute(self, request: ClassifyRequest) -> ClassifyResponse:
        payload = build_payload(request, self._settings)
        started = time.monotonic()
        response: dict[str, Any] | None = None
        error: str | None = None
        proposed = []
        try:
            response = await self._provider.complete(payload)
            proposed = labels(request, content(response))
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:500]}"
        trace = AITrace(
            provider=(
                self._settings.openai_base_url
                if self._settings.provider_protocol == "openai"
                else self._settings.ollama_base_url
            ),
            model=str(payload["model"]),
            parameters=trace_parameters(self._settings, payload),
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            taxonomy_version=request.taxonomy.version,
            request_payload=payload,
            raw_response=response,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=error,
        )
        return ClassifyResponse(
            request_id=request.request_id,
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            news_id=request.news.id,
            news_version=request.news.version,
            classifier=IDENTITY.slug,
            node_id=self._settings.classifier_node_id,
            status=(
                ClassificationStatus.COMPLETED if error is None else ClassificationStatus.FAILED
            ),
            error=(
                None
                if error is None
                else ClassificationError(
                    code="provider_error",
                    message="classifier provider request failed",
                    retryable=True,
                )
            ),
            labels=proposed,
            skipped=(
                []
                if error is None
                else request.options.allowed_axes or [axis.slug for axis in request.taxonomy.facets]
            ),
            trace=trace,
        )
