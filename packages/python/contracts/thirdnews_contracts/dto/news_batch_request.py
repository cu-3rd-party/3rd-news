from typing import Any

from pydantic import Field

from .contract_model import ContractModel
from .news_submission import NewsSubmission

MAX_BATCH_ITEMS = 200
type BatchSubmission = NewsSubmission | dict[str, Any]


class NewsBatchRequest(ContractModel):
    items: list[BatchSubmission] = Field(min_length=1, max_length=MAX_BATCH_ITEMS)
