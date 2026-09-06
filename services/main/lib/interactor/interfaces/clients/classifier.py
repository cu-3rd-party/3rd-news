from typing import Protocol

from thirdnews_contracts import ClassifyRequest

from lib.dto.classifier_dispatch import ClassifierDispatch


class ClassifierGateway(Protocol):
    async def classify(
        self,
        endpoint: str,
        request: ClassifyRequest,
        *,
        target_node_id: str | None = None,
    ) -> ClassifierDispatch: ...
