from dataclasses import dataclass

from lib.dto.object_info import ObjectInfo


@dataclass(frozen=True, slots=True)
class CompletedObject(ObjectInfo):
    source_key: str
