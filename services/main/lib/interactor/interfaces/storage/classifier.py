import uuid
from typing import Any, Protocol


class ClassifierStorage(Protocol):
    async def list_classifiers(self) -> list[dict[str, Any]]: ...

    async def create_classifier(self, values: dict[str, Any], actor: str) -> dict[str, Any]: ...

    async def update_classifier(
        self, classifier_id: uuid.UUID, values: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...

    async def delete_classifier(self, classifier_id: uuid.UUID, actor: str) -> None: ...

    async def set_classifier_signing_key(
        self, classifier_id: uuid.UUID, signing_public_key: str | None, actor: str
    ) -> dict[str, Any]: ...

    async def classifier_probe_target(self, classifier_id: uuid.UUID) -> tuple[str, float]: ...

    async def record_classifier_probe(
        self, classifier_id: uuid.UUID, error: str | None
    ) -> None: ...
