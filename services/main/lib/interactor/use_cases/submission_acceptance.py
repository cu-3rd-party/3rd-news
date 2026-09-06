from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from lib.domain import SubmissionIdentity
from lib.dto.accepted_submission import AcceptedSubmission
from lib.interactor.errors import ConflictError, ValidationError
from lib.interactor.interfaces.storage.labels import LabelStorage
from lib.interactor.interfaces.storage.submission_identity import SubmissionIdentityStorage
from lib.interactor.interfaces.storage.submission_writer import SubmissionWriterStorage


class SubmissionAcceptance:
    def __init__(
        self,
        unit_of_work_factory: Any,
        *,
        cooldown_seconds: float,
        max_attempts: int,
        label_storage: LabelStorage,
        identity_storage: SubmissionIdentityStorage,
        writer_storage: SubmissionWriterStorage,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.cooldown_seconds = cooldown_seconds
        self.max_attempts = max_attempts
        self.label_storage = label_storage
        self.identity_storage = identity_storage
        self.writer_storage = writer_storage

    async def execute(
        self,
        payload: Any,
        *,
        principal_id: str,
        bound_source_id: uuid.UUID | None = None,
        header_idempotency_key: str | None = None,
    ) -> AcceptedSubmission:
        source_slug = getattr(payload, "source", None) or getattr(payload, "source_key", None)
        external_id = getattr(payload, "external_id", None)
        payload_key = getattr(payload, "idempotency_key", None)
        if payload_key and header_idempotency_key and payload_key != header_idempotency_key:
            raise ConflictError("payload and header idempotency keys differ")
        idempotency_key = payload_key or header_idempotency_key
        if idempotency_key and len(idempotency_key) > 500:
            raise ValidationError("idempotency key must not exceed 500 characters")
        try:
            identity = SubmissionIdentity(source_slug, external_id, idempotency_key)
        except ValueError as error:
            raise ValidationError(str(error)) from error
        raw = payload.model_dump(mode="json", exclude_none=True)
        if idempotency_key is not None:
            raw["idempotency_key"] = idempotency_key
        digest = hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()

        async with self.unit_of_work_factory() as uow:
            try:
                existing = await self.identity_storage.find(uow, identity, bound_source_id)
                if existing is not None:
                    if existing.payload_hash != digest:
                        raise ConflictError(
                            "the idempotency identity is already bound to another payload"
                        )
                    return AcceptedSubmission(existing.id, "duplicate", existing.received_at)
                return await self.writer_storage.write(
                    uow,
                    payload,
                    raw,
                    digest,
                    source_slug,
                    external_id,
                    idempotency_key,
                    principal_id,
                    bound_source_id,
                    self.cooldown_seconds,
                    self.max_attempts,
                    self.label_storage,
                )
            except IntegrityError:
                await uow.rollback()
                existing = await self.identity_storage.find(uow, identity, bound_source_id)
                if existing is not None and existing.payload_hash == digest:
                    return AcceptedSubmission(existing.id, "duplicate", existing.received_at)
                raise ConflictError("submission identity was accepted concurrently") from None
