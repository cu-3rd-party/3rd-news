import asyncio
import inspect
from collections.abc import Sequence
from typing import cast

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..dto.classification_status import ClassificationStatus
from ..dto.classifier_manifest import ClassifierManifest
from ..dto.classify_request import ClassifyRequest
from ..dto.classify_response import ClassifyResponse
from ..dto.proposed_label import ProposedLabel
from ..interactor.errors.signature import SignatureError
from ..interactor.interfaces.clients.callback import CallbackGateway
from ..interactor.interfaces.clients.classifier import ClassifyFn, DeferredClassification
from ..interactor.interfaces.storage.replay import ReplayStorage
from ..interactor.use_cases.sign_message import KeyInput, bearer_token
from ..interactor.use_cases.verify_message import verify_message


def build_classifier_router(
    *,
    slug: str,
    name: str,
    node_id: str,
    classify: ClassifyFn,
    caller_public_key: KeyInput | None,
    expected_issuer: str,
    audience: str,
    version: str,
    replay_storage: ReplayStorage,
    callback_client: CallbackGateway | None = None,
    axes: list[str] | None = None,
    description: str | None = None,
    supports_async: bool = False,
    background: set[asyncio.Task[None]] | None = None,
) -> APIRouter:
    tasks = background if background is not None else set()
    manifest = ClassifierManifest(
        slug=slug,
        name=name,
        version=version,
        axes=axes or ["*"],
        supports_async=supports_async,
        description=description,
    )
    router = APIRouter()

    def readiness() -> None:
        if caller_public_key is None:
            raise HTTPException(status_code=503, detail="caller public key is not configured")
        if supports_async and callback_client is None:
            raise HTTPException(status_code=503, detail="callback signing key is not configured")

    @router.get("/health/healthz")
    @router.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok", "classifier": slug, "node_id": node_id}

    @router.get("/health/startup")
    @router.get("/health/ready")
    async def ready() -> dict[str, str]:
        readiness()
        return {"status": "ready", "classifier": slug, "node_id": node_id}

    @router.get("/manifest", response_model=ClassifierManifest)
    async def get_manifest() -> ClassifierManifest:
        return manifest

    @router.post("/classify", response_model=None)
    async def do_classify(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> ClassifyResponse | JSONResponse:
        raw = await request.body()
        try:
            payload = ClassifyRequest.model_validate_json(raw)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        readiness()
        if caller_public_key is None:
            raise HTTPException(status_code=503, detail="caller public key is not configured")
        try:
            verify_message(
                caller_public_key,
                bearer_token(authorization),
                raw,
                issuer=expected_issuer,
                audience=audience,
                job_id=payload.job_id,
                attempt_id=payload.attempt_id,
                node_id=node_id,
                replay_guard=replay_storage.accept_once,
            )
        except SignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        result = classify(payload)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, DeferredClassification):
            if not supports_async or payload.options.callback is None or callback_client is None:
                raise HTTPException(status_code=422, detail="async callback was not negotiated")
            task = asyncio.create_task(callback_client.deliver(payload, result.result))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            return JSONResponse(
                status_code=202,
                content={
                    "contract_version": "2.0",
                    "request_id": payload.request_id,
                    "job_id": payload.job_id,
                    "attempt_id": payload.attempt_id,
                    "status": "accepted",
                },
            )
        if isinstance(result, ClassifyResponse):
            return result
        labels = cast(Sequence[ProposedLabel], result)
        return ClassifyResponse(
            request_id=payload.request_id,
            job_id=payload.job_id,
            attempt_id=payload.attempt_id,
            news_id=payload.news.id,
            news_version=payload.news.version,
            classifier=slug,
            node_id=node_id,
            status=ClassificationStatus.COMPLETED,
            labels=list(labels),
        )

    return router
