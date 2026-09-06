from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test.settings import get_test_settings


@pytest.fixture
async def integration_database():
    settings = get_test_settings()
    if not settings.configured:
        pytest.skip("atomic TEST_DB_* settings are not configured")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        yield factory
    finally:
        await engine.dispose()
