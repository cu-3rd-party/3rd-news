from typing import Any, Protocol


class SubmissionIdentityStorage(Protocol):
    async def find(self, uow: Any, identity: Any, bound_source_id: Any) -> Any: ...

    async def source(self, uow: Any, slug: str | None, bound_source_id: Any) -> Any: ...
