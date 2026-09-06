from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol

from lib.dto.byte_range import ByteRange
from lib.dto.completed_object import CompletedObject
from lib.dto.object_info import ObjectInfo
from lib.dto.presigned_upload import PresignedUpload


class ObjectStore(Protocol):
    async def create_upload(
        self,
        *,
        owner_id: str,
        intent_id: str,
        size: int,
        content_type: str,
        sha256: str,
    ) -> PresignedUpload: ...

    async def complete_upload(
        self,
        *,
        temporary_key: str,
        owner_id: str,
        intent_id: str,
        expected_size: int,
        expected_content_type: str,
        expected_sha256: str,
    ) -> CompletedObject: ...

    async def stat(self, key: str) -> ObjectInfo: ...

    def read(self, key: str, *, byte_range: ByteRange | None = None) -> AsyncIterator[bytes]: ...

    async def delete(self, key: str) -> None: ...

    def objects_before(self, cutoff: datetime) -> AsyncIterator[str]: ...

    async def ready(self) -> None: ...

    async def close(self) -> None: ...
