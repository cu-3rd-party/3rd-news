from .batch_item_result import BatchItemResult
from .contract_model import ContractModel


class BatchIngestResult(ContractModel):
    results: list[BatchItemResult]
