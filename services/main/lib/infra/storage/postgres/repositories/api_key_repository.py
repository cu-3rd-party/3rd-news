from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from lib.infra.storage.postgres.models import ApiKey
from lib.interactor.errors import ConflictError, NotFoundError
from lib.interactor.interfaces.storage.api_key import ApiKeyStorage
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .catalog_repository_base import CatalogRepositoryBase


class ApiKeyRepository(CatalogRepositoryBase, ApiKeyStorage):
    async def list_api_keys(self) -> list[dict[str, Any]]:
        rows = (await self.session.scalars(select(ApiKey).order_by(ApiKey.created_at.desc()))).all()
        return [self.key_values(item) for item in rows]

    async def create_api_key(self, values: dict[str, Any], actor: str) -> dict[str, Any]:
        item = ApiKey(**values)
        self.session.add(item)
        try:
            await self.session.flush()
            self.persistence.add_audit(
                actor=actor,
                action="create",
                entity_type="api_key",
                entity_id=item.id,
                payload={"scopes": item.scopes},
            )
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            raise ConflictError("API key conflicts with existing data") from error
        return self.key_values(item)

    async def revoke_api_key(self, key_id: uuid.UUID, actor: str) -> dict[str, Any]:
        item = await self.session.get(ApiKey, key_id, with_for_update=True)
        if item is None:
            raise NotFoundError("API key not found")
        item.enabled = False
        item.revoked_at = datetime.now(UTC)
        self.persistence.add_audit(
            actor=actor, action="revoke", entity_type="api_key", entity_id=item.id
        )
        await self.session.commit()
        return self.key_values(item)

    @staticmethod
    def key_values(item: ApiKey) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "name": item.name,
            "prefix": item.prefix,
            "scopes": item.scopes,
            "source_id": str(item.source_id) if item.source_id else None,
            "filter_preset": item.filter_preset,
            "enabled": item.enabled,
            "expires_at": item.expires_at,
            "revoked_at": item.revoked_at,
            "last_used_at": item.last_used_at,
            "created_at": item.created_at,
        }
