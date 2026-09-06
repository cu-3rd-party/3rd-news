from typing import Annotated, Any

from pydantic import Field

from .callback_spec import CallbackSpec
from .contract_model import ContractModel


class ClassifyOptions(ContractModel):
    allowed_axes: list[str] = Field(default_factory=list)
    min_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    config: dict[str, Any] = Field(default_factory=dict)
    callback: CallbackSpec | None = None
