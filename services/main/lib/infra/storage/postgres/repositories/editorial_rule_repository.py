from __future__ import annotations

import uuid
from typing import Any

from lib.infra.storage.postgres.models import EditorialRule
from lib.interactor.errors import ConflictError, NotFoundError, ValidationError
from lib.interactor.interfaces.storage.editorial_rule import EditorialRuleStorage
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from .catalog_repository_base import CatalogRepositoryBase


class EditorialRuleRepository(CatalogRepositoryBase, EditorialRuleStorage):
    async def list_editorial_rules(self) -> list[dict[str, Any]]:
        rows = (
            await self.session.scalars(
                select(EditorialRule).order_by(EditorialRule.name, EditorialRule.version.desc())
            )
        ).all()
        return [self.editorial_rule_values(item) for item in rows]

    async def create_editorial_rule(self, values: dict[str, Any], actor: str) -> dict[str, Any]:
        latest = await self.session.scalar(
            select(func.max(EditorialRule.version)).where(EditorialRule.name == values["name"])
        )
        item = EditorialRule(version=int(latest or 0) + 1, **values)
        await self.session.execute(
            update(EditorialRule)
            .where(EditorialRule.name == values["name"], EditorialRule.enabled.is_(True))
            .values(enabled=False)
        )
        self.session.add(item)
        try:
            await self.session.flush()
            self.persistence.enqueue_rematerialization(scope="all")
            self.persistence.add_audit(
                actor=actor,
                action="create",
                entity_type="editorial_rule",
                entity_id=item.id,
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("editorial rule was revised concurrently") from error
        return self.editorial_rule_values(item)

    async def revise_editorial_rule(
        self, rule_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        previous = await self.session.get(EditorialRule, rule_id)
        if previous is None:
            raise NotFoundError("editorial rule not found")
        if values["name"] != previous.name:
            raise ValidationError("a rule revision cannot change its name")
        return await self.create_editorial_rule(values, actor)

    async def disable_editorial_rule(self, rule_id: uuid.UUID, actor: str) -> None:
        previous = await self.session.get(EditorialRule, rule_id)
        if previous is None:
            raise NotFoundError("editorial rule not found")
        await self.create_editorial_rule(
            {"name": previous.name, "enabled": False, "definition": previous.definition}, actor
        )

    @staticmethod
    def editorial_rule_values(item: EditorialRule) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "name": item.name,
            "version": item.version,
            "enabled": item.enabled,
            "definition": item.definition,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
