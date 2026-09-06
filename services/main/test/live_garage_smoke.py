from __future__ import annotations

import asyncio

from lib.core.config import Settings
from lib.infra.storage.s3 import ByteRange, S3ObjectStore


async def exercise() -> tuple[int, bytes]:
    settings = Settings()
    store = S3ObjectStore(
        endpoint_url=settings.file_endpoint,
        public_endpoint_url=settings.file_public_endpoint,
        bucket=settings.file_bucket,
        access_key=settings.file_access_key_value,
        secret_key=settings.file_secret_key_value,
        region=settings.file_region,
        max_upload_bytes=settings.upload_max_bytes,
    )
    payload = b"private-garage-smoke-payload"
    created = await store.put_bytes(
        payload,
        content_type="text/plain",
        owner_id="qa",
        source_id="live-smoke",
    )
    try:
        stored = await store.stat(created.key)
        assert stored.size == len(payload)
        assert stored.sha256 == created.sha256
        selected = b"".join(
            [
                chunk
                async for chunk in store.read(
                    created.key,
                    byte_range=ByteRange(8, 13, len(payload)),
                )
            ]
        )
        assert selected == payload[8:14]
        return stored.size, selected
    finally:
        async with store._client() as client:
            await client.delete_object(Bucket=settings.file_bucket, Key=created.key)


if __name__ == "__main__":
    size, selected = asyncio.run(exercise())
    print(f"Garage write/stat/range/delete size={size}; range={selected!r}")
