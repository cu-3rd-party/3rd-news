from __future__ import annotations

import uuid
from typing import Any

from lib.core.config import TAXONOMY_REVISION_LOCK_ID
from lib.infra.storage.postgres.models import Facet, FacetValue, Setting
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError
from lib.interactor.interfaces.storage.taxonomy_repository import TaxonomyRepository
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .persistence_repository import PersistenceRepository


class SqlAlchemyTaxonomyRepository(TaxonomyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.persistence = PersistenceRepository(session)

    async def list_facets(self) -> list[dict[str, Any]]:
        rows = (
            (
                await self.session.execute(
                    select(Facet).options(selectinload(Facet.values)).order_by(Facet.position)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return [
            {
                **self._facet_values(item),
                "values": [self._value_values(value) for value in item.values],
            }
            for item in rows
        ]

    async def create_facet(self, values: dict[str, Any], actor: str) -> dict[str, Any]:
        item = Facet(**values)
        self.session.add(item)
        try:
            await self.session.flush()
            await self._advance_taxonomy_revision()
            self.persistence.add_audit(
                actor=actor,
                action="create",
                entity_type="facet",
                entity_id=item.id,
                payload={"slug": item.slug},
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("facet already exists") from error
        return self._facet_values(item)

    async def update_facet(
        self, facet_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        item = await self.session.get(Facet, facet_id, with_for_update=True)
        if item is None:
            raise NotFoundError("facet not found")
        if values.get("slug") != item.slug or values.get("kind") != item.kind:
            raise ValidationError("facet slug and kind are immutable")
        for key, value in values.items():
            setattr(item, key, value)
        item.version += 1
        await self._advance_taxonomy_revision()
        self.persistence.enqueue_rematerialization(scope="facet", scope_id=facet_id)
        self.persistence.add_audit(
            actor=actor, action="update", entity_type="facet", entity_id=item.id
        )
        await self.session.commit()
        return self._facet_values(item)

    async def disable_facet(self, facet_id: uuid.UUID, actor: str) -> None:
        item = await self.session.get(Facet, facet_id, with_for_update=True)
        if item is None:
            raise NotFoundError("facet not found")
        item.enabled = False
        item.version += 1
        await self._advance_taxonomy_revision()
        self.persistence.enqueue_rematerialization(scope="facet", scope_id=facet_id)
        self.persistence.add_audit(
            actor=actor, action="delete", entity_type="facet", entity_id=item.id
        )
        await self.session.commit()

    async def create_value(
        self, facet_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        facet = await self.session.get(Facet, facet_id, with_for_update=True)
        if facet is None:
            raise NotFoundError("facet not found")
        item = FacetValue(facet_id=facet_id, **values)
        self.session.add(item)
        try:
            await self.session.flush()
            facet.version += 1
            await self._advance_taxonomy_revision()
            self.persistence.add_audit(
                actor=actor, action="create", entity_type="facet_value", entity_id=item.id
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("facet value already exists") from error
        return self._value_values(item)

    async def update_value(
        self, value_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        item = await self.session.get(FacetValue, value_id, with_for_update=True)
        if item is None:
            raise NotFoundError("facet value not found")
        if values.get("slug") != item.slug:
            raise ValidationError("facet value slug is immutable")
        facet = await self.session.get(Facet, item.facet_id, with_for_update=True)
        if facet is None:
            raise NotFoundError("facet not found")
        for key, value in values.items():
            setattr(item, key, value)
        facet.version += 1
        await self._advance_taxonomy_revision()
        self.persistence.enqueue_rematerialization(scope="value", scope_id=value_id)
        self.persistence.add_audit(
            actor=actor, action="update", entity_type="facet_value", entity_id=item.id
        )
        await self.session.commit()
        return self._value_values(item)

    async def disable_value(self, value_id: uuid.UUID, actor: str) -> None:
        item = await self.session.get(FacetValue, value_id, with_for_update=True)
        if item is None:
            raise NotFoundError("facet value not found")
        facet = await self.session.get(Facet, item.facet_id, with_for_update=True)
        if facet is None:
            raise NotFoundError("facet not found")
        item.enabled = False
        facet.version += 1
        await self._advance_taxonomy_revision()
        self.persistence.enqueue_rematerialization(scope="value", scope_id=value_id)
        self.persistence.add_audit(
            actor=actor, action="delete", entity_type="facet_value", entity_id=item.id
        )
        await self.session.commit()

    async def _advance_taxonomy_revision(self) -> int:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": TAXONOMY_REVISION_LOCK_ID}
        )
        setting = await self.session.get(Setting, "taxonomy_revision", with_for_update=True)
        if setting is None:
            setting = Setting(key="taxonomy_revision", value={"revision": 1})
            self.session.add(setting)
            await self.session.flush()
            return 1
        revision = int(setting.value.get("revision") or 0) + 1
        setting.value = {"revision": revision}
        return revision

    @staticmethod
    def _facet_values(item: Facet) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "slug": item.slug,
            "title": item.title,
            "description": item.description,
            "ai_hint": item.ai_hint,
            "kind": item.kind,
            "required": item.required,
            "enabled": item.enabled,
            "position": item.position,
            "version": item.version,
        }

    @staticmethod
    def _value_values(item: FacetValue) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "facet_id": str(item.facet_id),
            "slug": item.slug,
            "title": item.title,
            "description": item.description,
            "ai_hint": item.ai_hint,
            "synonyms": item.synonyms,
            "match_patterns": item.match_patterns,
            "enabled": item.enabled,
            "position": item.position,
        }
