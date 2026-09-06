from typing import Any

from pydantic import BaseModel, ConfigDict


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    params: dict[str, Any]
    summary: dict[str, Any]
