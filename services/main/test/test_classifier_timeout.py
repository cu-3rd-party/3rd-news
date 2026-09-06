import asyncio
from typing import Any, cast
from uuid import uuid4

from lib.dto.claimed_attempt import ClaimedAttempt
from lib.infra.storage.postgres.pipeline import SqlAlchemyPipelineStorage
from lib.interactor.use_cases.processing.pipeline_worker import PipelineWorker


async def test_node_deadline_cancels_dispatch_and_records_retry(monkeypatch):
    cancelled = asyncio.Event()
    failures = []

    class SlowClassifier:
        async def classify(self, *args, **kwargs):
            try:
                await asyncio.sleep(5)
            finally:
                cancelled.set()

    worker = PipelineWorker(
        cast(Any, None),
        cast(Any, SlowClassifier()),
        storage=SqlAlchemyPipelineStorage(),
        node_id="qa",
        public_base_url="https://api.example.edu",
        callback_audience="api",
    )

    async def prepare(claim):
        return object(), "https://node.example.edu", "node", 0.01

    async def fail(claim, error, **kwargs):
        failures.append(error)

    monkeypatch.setattr(worker, "prepare_request", prepare)
    monkeypatch.setattr(worker, "fail", fail)
    await worker.process(ClaimedAttempt(uuid4(), uuid4(), 1))
    assert cancelled.is_set()
    assert len(failures) == 1 and isinstance(failures[0], TimeoutError)
