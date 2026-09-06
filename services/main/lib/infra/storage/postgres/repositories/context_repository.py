from __future__ import annotations

from typing import Any

from lib.core.config import CLASSIFIER_EXAMPLE_DEFAULT_COUNT, CLASSIFIER_EXAMPLE_MAX_COUNT
from lib.infra.storage.postgres.models import Setting
from lib.interactor.interfaces.storage.context import ContextStorage

from .catalog_repository_base import CatalogRepositoryBase
from .classifier_example_repository import ClassifierExampleRepository


class ContextRepository(CatalogRepositoryBase, ContextStorage):
    async def get_setting(self, key: str) -> dict[str, Any] | None:
        item = await self.session.get(Setting, key)
        return dict(item.value) if item else None

    async def set_setting(self, key: str, value: dict[str, Any], actor: str) -> dict[str, Any]:
        item = await self.session.get(Setting, key, with_for_update=True)
        if item is None:
            item = Setting(key=key, value={})
            self.session.add(item)
        item.value = value
        self.persistence.add_audit(
            actor=actor,
            action="update",
            entity_type="setting",
            entity_id=item.key,
            payload=value,
        )
        await self.session.commit()
        return value

    async def classification_context(self) -> dict[str, Any]:
        value = await self.get_setting("classification_context") or {}
        limit = min(
            max(int(value.get("examples_limit") or CLASSIFIER_EXAMPLE_DEFAULT_COUNT), 1),
            CLASSIFIER_EXAMPLE_MAX_COUNT,
        )
        enabled = value.get("examples_enabled") is True
        count = (
            await ClassifierExampleRepository(self.session).eligible_count(limit=limit)
            if enabled
            else 0
        )
        return {
            "text": str(value.get("text") or ""),
            "examples_enabled": enabled,
            "example_count": count,
            "examples_configured": limit,
        }
