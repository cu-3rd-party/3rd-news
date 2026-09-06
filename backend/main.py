from granian import Granian
from granian.constants import HTTPModes, Interfaces, Loops
from granian.log import LogLevels

from lib.core.config import get_settings


def main(*, reload: bool = False) -> None:
    settings = get_settings()
    server = Granian(
        "lib.app:create_app",
        address=settings.backend_host,
        port=settings.backend_port,
        interface=Interfaces.ASGI,
        http=HTTPModes(settings.granian_http),
        workers=settings.backend_workers,
        factory=True,
        log_level=LogLevels(settings.logging_level.lower()),
        log_access=settings.granian_log_access_enabled,
        loop=Loops.uvloop,
        reload=reload,
    )
    server.serve()


if __name__ == "__main__":
    main()
