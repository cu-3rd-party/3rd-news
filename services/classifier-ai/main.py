from granian import Granian
from granian.constants import Interfaces, Loops

from lib.core.config import get_settings


def main() -> None:
    settings = get_settings()
    Granian(
        "lib.app:create_app",
        address=settings.host,
        port=settings.port,
        interface=Interfaces.ASGI,
        factory=True,
        loop=Loops.asyncio,
    ).serve()


if __name__ == "__main__":
    main()
