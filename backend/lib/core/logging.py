import logging
import logging.config

from lib.core.config import Settings


def configure_logging(settings: Settings) -> None:
    level = settings.logging_level.upper()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "[%(asctime)s] [%(levelname)s] [%(name)s] "
                    "%(message)s (%(filename)s:%(lineno)d)",
                },
                "access": {
                    "format": "[%(asctime)s] [%(levelname)s] %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stderr",
                },
                "access_console": {
                    "class": "logging.StreamHandler",
                    "formatter": "access",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "granian": {
                    "handlers": ["console"],
                    "level": level,
                    "propagate": False,
                },
                "granian.access": {
                    "handlers": ["access_console"],
                    "level": "INFO" if settings.granian_log_access_enabled else "WARNING",
                    "propagate": False,
                },
                "asyncpg": {
                    "handlers": ["console"],
                    "level": level,
                    "propagate": False,
                },
            },
            "root": {
                "handlers": ["console"],
                "level": level,
            },
        }
    )
