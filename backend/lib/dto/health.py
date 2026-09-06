from typing import Literal

from pydantic import BaseModel, ConfigDict


class LivenessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "ready", "not_ready"]
    dependencies: dict[str, bool]
