from __future__ import annotations

from typing import Any

from lib.dto.claimed_attempt import ClaimedAttempt
from lib.dto.pipeline_runtime import PipelineRuntime
from lib.interactor.interfaces.storage.pipeline import PipelineStorage

from .callback import PipelineCallback
from .claiming import PipelineClaiming
from .finalizer import PipelineFinalizer
from .raw_retention import PipelineRawRetention
from .request_builder import PipelineRequestBuilder
from .result_applier import PipelineResultApplier


class SqlAlchemyPipelineStorage(PipelineStorage):
    async def claim(self, runtime: PipelineRuntime) -> ClaimedAttempt | None:
        return await PipelineClaiming().claim(runtime)

    async def purge(self, runtime: PipelineRuntime) -> int:
        return await PipelineRawRetention().purge(runtime)

    async def build_request(
        self, runtime: PipelineRuntime, claimed: ClaimedAttempt
    ) -> tuple[Any, str, str, float]:
        return await PipelineRequestBuilder().build(runtime, claimed)

    async def mark_waiting(
        self, runtime: PipelineRuntime, claimed: ClaimedAttempt, raw_body: bytes
    ) -> None:
        await PipelineFinalizer().mark_waiting(runtime, claimed, raw_body)

    async def apply_result(
        self,
        runtime: PipelineRuntime,
        claimed: ClaimedAttempt,
        response: Any,
        raw_body: bytes,
        *,
        callback_token_hash: str | None = None,
    ) -> None:
        await PipelineResultApplier().apply(
            runtime,
            claimed,
            response,
            raw_body,
            callback_token_hash=callback_token_hash,
        )

    async def fail(
        self,
        runtime: PipelineRuntime,
        claimed: ClaimedAttempt,
        error: Exception,
        *,
        callback_token_hash: str | None = None,
        raw_body: bytes | None = None,
        retryable: bool = True,
    ) -> None:
        await PipelineFinalizer().fail(
            runtime,
            claimed,
            error,
            callback_token_hash=callback_token_hash,
            raw_body=raw_body,
            retryable=retryable,
        )

    async def apply_callback(
        self, runtime: PipelineRuntime, raw_body: bytes, authorization: str | None
    ) -> str:
        return await PipelineCallback().apply(runtime, raw_body, authorization)
