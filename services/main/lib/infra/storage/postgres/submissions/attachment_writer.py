from __future__ import annotations

import uuid
from typing import Any

from lib.infra.storage.postgres.models import Attachment, News, Submission, UploadIntent
from lib.interactor.errors import ConflictError, ValidationError
from lib.interactor.interfaces.storage.unit_of_work import UnitOfWork


class SubmissionAttachmentWriter:
    async def write(
        self,
        uow: UnitOfWork,
        submission: Submission,
        news: News,
        payload: Any,
        principal_id: str,
    ) -> None:
        for position, item in enumerate(getattr(payload, "attachments", ())):
            intent = None
            upload_id = getattr(item, "upload_id", None) or getattr(item, "upload_intent_id", None)
            attachment = Attachment(
                submission_id=submission.id,
                news_id=news.id,
                original_url=self.string_value(getattr(item, "url", None)),
                filename=getattr(item, "filename", None),
                content_type=getattr(item, "content_type", None) or getattr(item, "mime", None),
                kind=str(getattr(item, "kind", "file")).split(".")[-1].lower(),
                caption=getattr(item, "caption", None),
                position=getattr(item, "position", position),
            )
            if upload_id:
                try:
                    intent_uuid = uuid.UUID(str(upload_id))
                except ValueError as error:
                    raise ValidationError("upload intent id is invalid") from error
                intent = await uow.session.get(UploadIntent, intent_uuid)
                if (
                    intent is None
                    or intent.owner_id != principal_id
                    or intent.status != "completed"
                    or intent.attachment_id is not None
                ):
                    raise ConflictError(
                        "upload intent is missing, incomplete, or belongs to another principal"
                    )
                attachment.object_key = intent.final_key
                attachment.size = intent.expected_size
                attachment.content_type = intent.content_type
                attachment.sha256 = intent.sha256
                attachment.status = "stored"
            uow.session.add(attachment)
            await uow.session.flush()
            if upload_id and intent is not None:
                intent.attachment_id = attachment.id

    @staticmethod
    def string_value(value: Any) -> str | None:
        return str(value) if value is not None else None
