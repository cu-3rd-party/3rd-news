from dataclasses import dataclass

from thirdnews_contracts import ClassifyResponse


@dataclass(frozen=True, slots=True)
class ClassifierDispatch:
    accepted: bool
    response: ClassifyResponse | None
    raw_body: bytes
    status: int
