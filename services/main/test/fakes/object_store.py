from types import SimpleNamespace
from uuid import uuid4


class ObjectStore:
    def __init__(self):
        self.keys = set()
        self.deleted = []

    async def put_bytes(self, data, *, content_type, owner_id, source_id):
        del owner_id, source_id
        key = f"objects/{uuid4()}"
        self.keys.add(key)
        return SimpleNamespace(
            key=key,
            size=len(data),
            sha256="a" * 64,
            content_type=content_type,
        )

    async def delete(self, key):
        self.deleted.append(key)
        self.keys.discard(key)

    async def objects_before(self, cutoff):
        del cutoff
        for key in list(self.keys):
            yield key
