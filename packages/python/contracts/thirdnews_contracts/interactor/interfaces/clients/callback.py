from abc import ABC, abstractmethod
from collections.abc import Awaitable

from ....dto.classify_request import ClassifyRequest
from ....dto.classify_response import ClassifyResponse


class CallbackGateway(ABC):
    @abstractmethod
    async def deliver(
        self,
        request: ClassifyRequest,
        awaitable: Awaitable[ClassifyResponse],
    ) -> None:
        raise NotImplementedError
