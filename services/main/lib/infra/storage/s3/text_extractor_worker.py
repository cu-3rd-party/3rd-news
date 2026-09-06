from __future__ import annotations

import json
import sys

from lib.core.config import (
    TEXT_EXTRACTION_CPU_MAX_SECONDS,
    TEXT_EXTRACTION_HEADER_MAX_BYTES,
    TEXT_EXTRACTION_INPUT_MAX_BYTES,
    TEXT_EXTRACTION_MEMORY_MAX_BYTES,
)


def apply_resource_limits() -> None:
    try:
        import resource
    except ImportError:
        return
    if sys.platform == "linux":
        _, address_space_hard = resource.getrlimit(resource.RLIMIT_AS)
        address_space_limit = (
            TEXT_EXTRACTION_MEMORY_MAX_BYTES
            if address_space_hard == resource.RLIM_INFINITY
            else min(TEXT_EXTRACTION_MEMORY_MAX_BYTES, address_space_hard)
        )
        resource.setrlimit(
            resource.RLIMIT_AS,
            (address_space_limit, address_space_limit),
        )
    _, cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
    cpu_soft = (
        TEXT_EXTRACTION_CPU_MAX_SECONDS
        if cpu_hard == resource.RLIM_INFINITY
        else min(TEXT_EXTRACTION_CPU_MAX_SECONDS, cpu_hard)
    )
    cpu_limit = cpu_soft + 1 if cpu_hard == resource.RLIM_INFINITY else cpu_hard
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (cpu_soft, cpu_limit),
    )


def main() -> int:
    header = sys.stdin.buffer.readline(TEXT_EXTRACTION_HEADER_MAX_BYTES + 1)
    if not header.endswith(b"\n") or len(header) > TEXT_EXTRACTION_HEADER_MAX_BYTES:
        return 2
    try:
        request = json.loads(header)
        content_type = request.get("content_type")
        filename = request.get("filename")
        max_characters = int(request["max_characters"])
    except KeyError, TypeError, ValueError:
        return 2
    if content_type is not None and not isinstance(content_type, str):
        return 2
    if filename is not None and not isinstance(filename, str):
        return 2
    apply_resource_limits()
    data = sys.stdin.buffer.read(TEXT_EXTRACTION_INPUT_MAX_BYTES + 1)
    if len(data) > TEXT_EXTRACTION_INPUT_MAX_BYTES:
        return 2
    try:
        from lib.infra.storage.s3.text_extractor import extract_text

        text = extract_text(
            data,
            content_type=content_type,
            filename=filename,
            max_characters=max_characters,
        )
        if text:
            sys.stdout.buffer.write(text.encode("utf-8"))
    except Exception:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
