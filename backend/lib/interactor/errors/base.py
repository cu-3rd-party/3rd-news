from typing import Any


class ServiceError(Exception):
    default_message = "Service error"
    default_status_code = 500
    default_code = "SERVICE_ERROR"

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        code: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.status_code = status_code or self.default_status_code
        self.code = code or self.default_code
        self.extra = extra or {}

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }

        if self.extra:
            error["extra"] = self.extra

        return {"error": error}
