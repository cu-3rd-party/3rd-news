from collections.abc import Awaitable, Callable, Sequence

from ....domain.entities.deferred_classification import DeferredClassification
from ....dto.classify_request import ClassifyRequest
from ....dto.classify_response import ClassifyResponse
from ....dto.proposed_label import ProposedLabel

type ClassifyResult = Sequence[ProposedLabel] | ClassifyResponse | DeferredClassification
type ClassifyFn = Callable[[ClassifyRequest], ClassifyResult | Awaitable[ClassifyResult]]
