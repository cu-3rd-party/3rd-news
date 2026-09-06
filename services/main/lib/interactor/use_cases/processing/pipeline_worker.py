from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from thirdnews_contracts import CallbackResult, ClassifyRequest

from lib.dto.claimed_attempt import ClaimedAttempt
from lib.dto.pipeline_runtime import PipelineRuntime
from lib.interactor.errors import StaleAttemptError
from lib.interactor.interfaces.clients.classifier import ClassifierGateway
from lib.interactor.interfaces.storage.pipeline import PipelineStorage

from .classification_response_policy import ClassificationResponsePolicy
from .raw_payloads import RawPayloadProtector


class PipelineWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client: ClassifierGateway,
        *,
        storage: PipelineStorage,
        node_id: str,
        public_base_url: str,
        callback_audience: str,
        callback_timeout_seconds: int = 300,
        request_timeout_seconds: float = 30.0,
        lease_seconds: int = 120,
        poll_seconds: float = 0.5,
        cooldown_seconds: int = 5,
        raw_retention_days: int = 30,
        raw_payload_protector: RawPayloadProtector | None = None,
    ) -> None:
        self.storage = storage
        self.runtime = PipelineRuntime(
            sessions=session_factory,
            client=client,
            node_id=node_id,
            public_base_url=public_base_url.rstrip("/"),
            callback_audience=callback_audience,
            callback_timeout=callback_timeout_seconds,
            request_timeout=request_timeout_seconds,
            lease_seconds=lease_seconds,
            poll_seconds=poll_seconds,
            cooldown=cooldown_seconds,
            raw_retention_days=raw_retention_days,
            protector=raw_payload_protector,
        )

    async def run(self, *, stop: asyncio.Event, concurrency: int = 4) -> None:
        async with asyncio.TaskGroup() as group:
            for _ in range(concurrency):
                group.create_task(self.run_slot(stop))
            group.create_task(self.purge_raw_loop(stop))

    async def purge_raw_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.purge_expired_raw_payloads()
            try:
                await asyncio.wait_for(stop.wait(), timeout=60 * 60)
            except TimeoutError:
                pass

    async def purge_expired_raw_payloads(self) -> int:
        return await self.storage.purge(self.runtime)

    async def run_slot(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                claimed = await self.claim_one()
            except DBAPIError as error:
                code = getattr(error.orig, "sqlstate", None)
                if code not in {"40P01", "40001"} and not error.connection_invalidated:
                    raise
                logging.getLogger(__name__).warning(
                    "Retrying worker claim after transaction conflict"
                )
                claimed = None
            if claimed is None:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.runtime.poll_seconds)
                except TimeoutError:
                    pass
                continue
            await self.process(claimed)

    async def claim_one(self) -> ClaimedAttempt | None:
        return await self.storage.claim(self.runtime)

    async def process(self, claimed: ClaimedAttempt) -> None:
        response_body: bytes | None = None
        try:
            request, endpoint, target_node_id, timeout = await self.prepare_request(claimed)
            async with asyncio.timeout(timeout):
                dispatched = await self.runtime.client.classify(
                    endpoint, request, target_node_id=target_node_id
                )
            response_body = dispatched.raw_body
            if dispatched.accepted:
                await self.mark_waiting(claimed, dispatched.raw_body)
            elif dispatched.response is not None:
                failure = self.classification_failure(dispatched.response)
                if failure is not None:
                    error, retryable = failure
                    await self.fail(
                        claimed,
                        error,
                        raw_body=dispatched.raw_body,
                        retryable=retryable,
                    )
                    return
                await self.apply_response(claimed, dispatched.response, dispatched.raw_body)
        except StaleAttemptError:
            return
        except Exception as error:
            await self.fail(
                claimed,
                error,
                raw_body=getattr(error, "raw_body", response_body),
            )

    async def prepare_request(
        self, claimed: ClaimedAttempt
    ) -> tuple[ClassifyRequest, str, str, float]:
        return await self.storage.build_request(self.runtime, claimed)

    async def mark_waiting(self, claimed: ClaimedAttempt, raw_body: bytes) -> None:
        await self.storage.mark_waiting(self.runtime, claimed, raw_body)

    async def apply_response(
        self,
        claimed: ClaimedAttempt,
        response: CallbackResult | Any,
        raw_body: bytes,
        *,
        callback_token_hash: str | None = None,
    ) -> None:
        await self.storage.apply_result(
            self.runtime,
            claimed,
            response,
            raw_body,
            callback_token_hash=callback_token_hash,
        )

    async def fail(
        self,
        claimed: ClaimedAttempt,
        error: Exception,
        *,
        callback_token_hash: str | None = None,
        raw_body: bytes | None = None,
        retryable: bool = True,
    ) -> None:
        await self.storage.fail(
            self.runtime,
            claimed,
            error,
            callback_token_hash=callback_token_hash,
            raw_body=raw_body,
            retryable=retryable,
        )

    async def apply_callback(self, raw_body: bytes, authorization: str | None) -> str:
        return await self.storage.apply_callback(self.runtime, raw_body, authorization)

    @staticmethod
    def classification_failure(response: CallbackResult | Any) -> tuple[Exception, bool] | None:
        return ClassificationResponsePolicy().failure(response)
