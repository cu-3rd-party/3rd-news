import asyncio

from lib.infra.clients.search import MeiliSearchClient, SearchIndexer
from lib.infra.storage.postgres import Database

from lib.core.config import Settings


async def main() -> None:
    settings = Settings()
    database = Database(settings.db_url)
    search = MeiliSearchClient(
        settings.search_url, settings.search_key_value, index=settings.search_index
    )
    try:
        count = await SearchIndexer(
            database.session_factory, search, owner="admin-reindex"
        ).reindex_all()
        print(f"Confirmed search projection for {count} published documents")
    finally:
        await search.close()
        await database.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
