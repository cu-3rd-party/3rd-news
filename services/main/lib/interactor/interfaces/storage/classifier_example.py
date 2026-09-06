import uuid
from typing import Protocol

from thirdnews_contracts import LabeledExample


class ClassifierExampleStorage(Protocol):
    async def list_examples(
        self,
        *,
        exclude_news_id: uuid.UUID | None,
        allowed_axes: set[str],
        limit: int,
    ) -> list[LabeledExample]: ...

    async def eligible_count(self, *, limit: int) -> int: ...
