from __future__ import annotations

from typing import Any, Protocol

from lib.dto.claimed_attempt import ClaimedAttempt
from lib.dto.pipeline_runtime import PipelineRuntime


class PipelineStorage(Protocol):
    async def claim(self, runtime: PipelineRuntime) -> ClaimedAttempt | None: ...

    async def purge(self, runtime: PipelineRuntime) -> int: ...

    async def build_request(
        self, runtime: PipelineRuntime, claimed: ClaimedAttempt
    ) -> tuple[Any, str, str, float]: ...

    async def mark_waiting(
        self, runtime: PipelineRuntime, claimed: ClaimedAttempt, raw_body: bytes
    ) -> None: ...

    async def apply_result(
        self,
        runtime: PipelineRuntime,
        claimed: ClaimedAttempt,
        response: Any,
        raw_body: bytes,
        *,
        callback_token_hash: str | None = None,
    ) -> None: ...

    async def fail(
        self,
        runtime: PipelineRuntime,
        claimed: ClaimedAttempt,
        error: Exception,
        *,
        callback_token_hash: str | None = None,
        raw_body: bytes | None = None,
        retryable: bool = True,
    ) -> None: ...

    async def apply_callback(
        self, runtime: PipelineRuntime, raw_body: bytes, authorization: str | None
    ) -> str: ...
