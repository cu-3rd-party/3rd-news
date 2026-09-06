import asyncio
from pathlib import Path

from lib.core.config import Settings


def main() -> None:
    settings = Settings()
    if settings.service_mode == "initialize":
        from lib.core.configuration_initializer import ConfigurationInitializer

        ConfigurationInitializer().initialize()
    elif settings.service_mode == "migrate":
        from alembic import command
        from alembic.config import Config

        config = Config(Path(__file__).with_name("alembic.ini"))
        config.set_main_option("sqlalchemy.url", settings.db_url)
        command.upgrade(config, "head")
    elif settings.service_mode == "api":
        from granian import Granian
        from granian.constants import Interfaces, Loops

        Granian(
            "lib.app:create_app",
            address=settings.api_host,
            port=settings.api_port,
            interface=Interfaces.ASGI,
            factory=True,
            workers=settings.api_workers,
            loop=Loops.uvloop,
            log_access=False,
        ).serve()
    elif settings.service_mode.startswith("worker-"):
        from lib.core.workers import run_worker

        asyncio.run(run_worker(settings.service_mode, settings))


if __name__ == "__main__":
    main()
