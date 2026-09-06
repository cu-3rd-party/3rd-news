from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from lib.infra.storage.postgres.models import AuthRateLimit, Session, User
from lib.interactor.interfaces.storage.auth_account import AuthAccountStorage
from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

AuthRateKey = tuple[str, str]


class AuthAccountRepository(AuthAccountStorage):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_user_by_email(self, email: str) -> User | None:
        return (
            await self.session.execute(
                select(User).where(func.lower(User.email) == email.strip().casefold())
            )
        ).scalar_one_or_none()

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        csrf_hash: str,
        expires_at: datetime,
    ) -> None:
        self.session.add(
            Session(
                user_id=user_id,
                token_hash=token_hash,
                csrf_hash=csrf_hash,
                expires_at=expires_at,
            )
        )

    async def find_session_by_hash(self, token_hash: str) -> Session | None:
        return (
            await self.session.execute(select(Session).where(Session.token_hash == token_hash))
        ).scalar_one_or_none()

    async def auth_rate_limited(self, keys: tuple[AuthRateKey, ...], moment: datetime) -> bool:
        if not keys:
            return False
        rows = (
            await self.session.scalars(
                select(AuthRateLimit).where(
                    or_(
                        *(
                            and_(
                                AuthRateLimit.scope == scope,
                                AuthRateLimit.identifier_hash == identifier_hash,
                            )
                            for scope, identifier_hash in keys
                        )
                    )
                )
            )
        ).all()
        return any(row.blocked_until is not None and row.blocked_until > moment for row in rows)

    async def record_auth_failure(
        self,
        keys: tuple[AuthRateKey, ...],
        *,
        moment: datetime,
        attempt_limit: int,
        window: timedelta,
        base_cooldown: timedelta,
        max_cooldown: timedelta,
    ) -> None:
        window_cutoff = moment - window
        for scope, identifier_hash in sorted(keys):
            statement = insert(AuthRateLimit).values(
                scope=scope,
                identifier_hash=identifier_hash,
                failure_count=1,
                window_started_at=moment,
                blocked_until=None,
                updated_at=moment,
            )
            expired = AuthRateLimit.window_started_at <= window_cutoff
            failure_count = (
                await self.session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[AuthRateLimit.scope, AuthRateLimit.identifier_hash],
                        set_={
                            "failure_count": case(
                                (expired, statement.excluded.failure_count),
                                else_=AuthRateLimit.failure_count + 1,
                            ),
                            "window_started_at": case(
                                (expired, statement.excluded.window_started_at),
                                else_=AuthRateLimit.window_started_at,
                            ),
                            "blocked_until": case(
                                (expired, None),
                                else_=AuthRateLimit.blocked_until,
                            ),
                            "updated_at": moment,
                        },
                    ).returning(AuthRateLimit.failure_count)
                )
            ).scalar_one()
            if failure_count < attempt_limit:
                continue
            exponent = min(failure_count - attempt_limit, 20)
            cooldown_seconds = min(
                max_cooldown.total_seconds(),
                base_cooldown.total_seconds() * 2**exponent,
            )
            blocked_until = moment + timedelta(seconds=cooldown_seconds)
            await self.session.execute(
                update(AuthRateLimit)
                .where(
                    AuthRateLimit.scope == scope,
                    AuthRateLimit.identifier_hash == identifier_hash,
                )
                .values(blocked_until=blocked_until, updated_at=moment)
            )

    async def clear_account_auth_failures(self, identifier_hash: str) -> None:
        await self.session.execute(
            delete(AuthRateLimit).where(
                AuthRateLimit.scope == "account",
                AuthRateLimit.identifier_hash == identifier_hash,
            )
        )

    async def commit(self) -> None:
        await self.session.commit()
