from __future__ import annotations

from typing import Any

from lib.infra.storage.postgres.models import Classifier, User
from lib.interactor.interfaces.storage.bootstrap import BootstrapStorage
from sqlalchemy import select


class SqlAlchemyBootstrapStorage(BootstrapStorage):
    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def initialize(
        self,
        *,
        admin_email: str,
        admin_password_hash: str | None,
        classifiers: list[dict[str, Any]],
    ) -> None:
        async with self.session_factory() as session:
            existing = await session.scalar(select(User.id).where(User.email == admin_email))
            if admin_password_hash is not None and existing is None:
                session.add(
                    User(email=admin_email, password_hash=admin_password_hash, role="admin")
                )
            for raw in classifiers:
                slug = str(raw["slug"])
                if await session.scalar(select(Classifier.id).where(Classifier.slug == slug)):
                    continue
                session.add(Classifier(**raw))
            await session.commit()
