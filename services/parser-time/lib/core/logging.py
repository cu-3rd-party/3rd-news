import logging

from .config import Settings


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(level=settings.logging_level.upper())
