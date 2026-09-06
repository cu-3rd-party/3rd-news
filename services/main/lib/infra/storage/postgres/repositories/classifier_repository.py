from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from lib.infra.storage.postgres.models import Classifier
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError
from lib.interactor.interfaces.storage.classifier import ClassifierStorage
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .catalog_repository_base import CatalogRepositoryBase


class ClassifierRepository(CatalogRepositoryBase, ClassifierStorage):
    async def list_classifiers(self) -> list[dict[str, Any]]:
        rows = (
            await self.session.scalars(select(Classifier).order_by(Classifier.priority.desc()))
        ).all()
        return [self.classifier_values(item) for item in rows]

    async def create_classifier(self, values: dict[str, Any], actor: str) -> dict[str, Any]:
        item = Classifier(**values)
        self.session.add(item)
        try:
            await self.session.flush()
            self.persistence.add_audit(
                actor=actor, action="create", entity_type="classifier", entity_id=item.id
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("classifier already exists") from error
        return self.classifier_values(item)

    async def update_classifier(
        self, classifier_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        item = await self.session.get(Classifier, classifier_id, with_for_update=True)
        if item is None:
            raise NotFoundError("classifier not found")
        if "slug" in values and values["slug"] != item.slug:
            raise ValidationError("classifier slug is immutable")
        policy_fields = {"enabled", "shadow", "priority", "allowed_axes", "min_confidence"}
        policy_changed = any(
            key in policy_fields and getattr(item, key) != value for key, value in values.items()
        )
        for key, value in values.items():
            setattr(item, key, value)
        if policy_changed:
            self.persistence.enqueue_rematerialization(scope="classifier", scope_id=item.slug)
        self.persistence.add_audit(
            actor=actor, action="update", entity_type="classifier", entity_id=item.id
        )
        await self.session.commit()
        return self.classifier_values(item)

    async def delete_classifier(self, classifier_id: uuid.UUID, actor: str) -> None:
        item = await self.session.get(Classifier, classifier_id, with_for_update=True)
        if item is None:
            raise NotFoundError("classifier not found")
        self.persistence.add_audit(
            actor=actor, action="delete", entity_type="classifier", entity_id=item.id
        )
        self.persistence.enqueue_rematerialization(scope="classifier", scope_id=item.slug)
        await self.session.delete(item)
        await self.session.commit()

    async def set_classifier_signing_key(
        self, classifier_id: uuid.UUID, signing_public_key: str | None, actor: str
    ) -> dict[str, Any]:
        item = await self.session.get(Classifier, classifier_id, with_for_update=True)
        if item is None:
            raise NotFoundError("classifier not found")
        item.signing_public_key = signing_public_key
        self.persistence.add_audit(
            actor=actor,
            action="rotate_signing_key" if signing_public_key else "clear_signing_key",
            entity_type="classifier",
            entity_id=item.id,
        )
        await self.session.commit()
        return self.classifier_values(item)

    async def classifier_probe_target(self, classifier_id: uuid.UUID) -> tuple[str, float]:
        item = await self.session.get(Classifier, classifier_id)
        if item is None:
            raise NotFoundError("classifier not found")
        return item.endpoint, item.timeout_seconds

    async def record_classifier_probe(self, classifier_id: uuid.UUID, error: str | None) -> None:
        item = await self.session.get(Classifier, classifier_id, with_for_update=True)
        if item is None:
            raise NotFoundError("classifier not found")
        item.last_error = error
        if error is None:
            item.last_ok_at = datetime.now(UTC)
        await self.session.commit()

    @staticmethod
    def classifier_values(item: Classifier) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "slug": item.slug,
            "name": item.name,
            "endpoint": item.endpoint,
            "allowed_axes": item.allowed_axes,
            "config": item.config,
            "has_signing_key": bool(item.signing_public_key),
            "enabled": item.enabled,
            "shadow": item.shadow,
            "priority": item.priority,
            "min_confidence": item.min_confidence,
            "timeout_seconds": item.timeout_seconds,
            "last_ok_at": item.last_ok_at,
            "last_error": item.last_error,
        }
