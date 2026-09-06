from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from lib.core.service_factory import service_factory
from lib.dto.pipeline_runtime import PipelineRuntime
from lib.interactor.errors import ClassifierProtocolError, StaleAttemptError
from lib.interactor.use_cases.processing.raw_payloads import RawPayloadProtector

router = APIRouter()


@router.post("/api/v1/classification/callback", status_code=202)
async def callback(request: Request) -> dict:
    settings = request.app.state.settings
    max_bytes = settings.classifier_response_max_bytes
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                raise HTTPException(413, "classifier callback is too large")
        except ValueError as error:
            raise HTTPException(400, "invalid Content-Length") from error
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, "classifier callback is too large")
        chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        runtime = PipelineRuntime(
            sessions=request.app.state.database.session_factory,
            client=None,
            node_id=settings.worker_node_id,
            public_base_url=settings.public_base_url,
            callback_audience=settings.callback_audience,
            callback_timeout=settings.callback_timeout_seconds,
            request_timeout=settings.classifier_request_timeout_seconds,
            lease_seconds=settings.worker_lease_seconds,
            poll_seconds=settings.worker_poll_seconds,
            cooldown=settings.pipeline_cooldown_seconds,
            raw_retention_days=settings.raw_audit_retention_days,
            protector=RawPayloadProtector(settings.raw_audit_encryption_key)
            if settings.raw_audit_encryption_key
            else None,
        )
        status = await service_factory.pipeline().apply_callback(
            runtime, raw, request.headers.get("authorization")
        )
    except PermissionError as error:
        raise HTTPException(401, "invalid callback signature") from error
    except StaleAttemptError as error:
        raise HTTPException(409, "callback attempt is stale") from error
    except (ClassifierProtocolError, LookupError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return {"status": status}
