from sqlalchemy.ext.asyncio import AsyncSession

from .persistence_repository import PersistenceRepository


class CatalogRepositoryBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.persistence = PersistenceRepository(session)
