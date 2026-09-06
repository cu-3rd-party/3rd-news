from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from typing import Any

import aiohttp

from tools.ops.load_http import authenticate, bearer, json_request
from tools.ops.load_measurement import Measurement
from tools.ops.load_security import negative_auth_checks
from tools.ops.load_settings import LoadSettings
from tools.ops.load_statistics import latency_summary
from tools.ops.load_wait import wait_for_news_id, wait_for_terminal_news


async def ensure_source(
    session: aiohttp.ClientSession, cfg: LoadSettings, headers: dict[str, str]
) -> dict[str, Any]:
    digest = hashlib.sha256(cfg.run_id.encode()).hexdigest()[:16]
    slug = f"synthetic-{cfg.mode}-{digest}"
    _, listing = await json_request(
        session,
        "GET",
        f"{cfg.base_url}/api/v1/admin/sources",
        expected={200},
        headers=headers,
    )
    for item in listing.get("items", []):
        if isinstance(item, dict) and item.get("slug") == slug:
            if bool(item.get("skip_classification")) != (cfg.mode == "queue"):
                raise RuntimeError("existing synthetic source has incompatible load mode")
            return item
    _, source = await json_request(
        session,
        "POST",
        f"{cfg.base_url}/api/v1/admin/sources",
        expected={201},
        headers=headers,
        json={
            "slug": slug,
            "title": f"Synthetic pipeline load {cfg.run_id}",
            "kind": "synthetic-load",
            "description": "Bounded disposable Compose load probe",
            "enabled": True,
            "skip_classification": cfg.mode == "queue",
            "default_labels": {},
        },
    )
    return source


async def measure_one(
    session: aiohttp.ClientSession,
    cfg: LoadSettings,
    headers: dict[str, str],
    source_slug: str,
    index: int,
    semaphore: asyncio.Semaphore,
    common_deadline: float,
) -> Measurement:
    payload = {
        "source": source_slug,
        "external_id": f"{cfg.run_id}:{index:03d}",
        "idempotency_key": f"pipeline-load:{cfg.run_id}:{index:03d}",
        "title": f"Synthetic load item {index:03d} [{cfg.run_id}]",
        "body_md": (
            "Synthetic pipeline load record. It contains no production data. "
            f"Correlation: {cfg.run_id}; sequence: {index:03d}."
        ),
        "source_text": "synthetic-load",
        "lang": "en",
        "extra": {"synthetic": True, "load_run_id": cfg.run_id, "sequence": index},
    }
    started = time.monotonic()
    async with semaphore:
        _, accepted = await json_request(
            session,
            "POST",
            f"{cfg.base_url}/api/v1/news",
            expected={202},
            headers=headers,
            json=payload,
        )
    accepted_at = time.monotonic()
    ingest_status = str(accepted.get("status", ""))
    if ingest_status == "duplicate" and not cfg.allow_duplicates:
        raise RuntimeError(
            f"item {index} was duplicate; choose a new LOAD_RUN_ID or set LOAD_ALLOW_DUPLICATES=1"
        )
    if ingest_status not in {"accepted", "duplicate"}:
        raise RuntimeError(f"item {index} returned unexpected ingest status {ingest_status!r}")
    submission_id = accepted.get("submission_id")
    if not isinstance(submission_id, str):
        raise TypeError(f"item {index} response has no submission_id")
    news_id = await wait_for_news_id(session, cfg, headers, submission_id, common_deadline)
    news_status = await wait_for_terminal_news(session, cfg, headers, news_id, common_deadline)
    completed_at = time.monotonic()
    return Measurement(
        index=index,
        ingest_status=ingest_status,
        submission_id=submission_id,
        news_id=news_id,
        news_status=news_status,
        accepted_ms=(accepted_at - started) * 1000,
        pipeline_ms=(completed_at - started) * 1000,
    )


async def run() -> dict[str, Any]:
    cfg = LoadSettings()
    timeout = aiohttp.ClientTimeout(total=max(cfg.timeout_seconds, 30), connect=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        token = await authenticate(session, cfg)
        headers = bearer(token)
        source = await ensure_source(session, cfg, headers)
        negative = (
            await negative_auth_checks(session, cfg, headers, source) if cfg.negative_checks else {}
        )
        semaphore = asyncio.Semaphore(cfg.concurrency)
        wall_started = time.monotonic()
        deadline = wall_started + cfg.timeout_seconds
        measurements = await asyncio.gather(
            *(
                measure_one(
                    session,
                    cfg,
                    headers,
                    str(source["slug"]),
                    index,
                    semaphore,
                    deadline,
                )
                for index in range(cfg.count)
            )
        )
        wall_seconds = time.monotonic() - wall_started

    accepted = [item.accepted_ms for item in measurements]
    pipeline = [item.pipeline_ms for item in measurements]
    return {
        "schema": "thirdnews.pipeline-load.v1",
        "run_id": cfg.run_id,
        "mode": cfg.mode,
        "classification_exercised": cfg.mode == "full",
        "interpretation": (
            "full pipeline including configured classifiers"
            if cfg.mode == "full"
            else "queue/outbox/pipeline baseline; source.skip_classification=true; excludes AI"
        ),
        "worker_pipeline_replicas_label": cfg.worker_replicas,
        "count": cfg.count,
        "concurrency": cfg.concurrency,
        "wall_seconds": round(wall_seconds, 3),
        "throughput_items_per_second": round(cfg.count / wall_seconds, 3),
        "accept_latency_ms": latency_summary(accepted),
        "pipeline_latency_ms": latency_summary(pipeline),
        "ingest_statuses": {
            status: sum(item.ingest_status == status for item in measurements)
            for status in sorted({item.ingest_status for item in measurements})
        },
        "news_statuses": {
            status: sum(item.news_status == status for item in measurements)
            for status in sorted({item.news_status for item in measurements})
        },
        "negative_auth_checks": negative,
    }


def main() -> None:
    try:
        result = asyncio.run(run())
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": "thirdnews.pipeline-load.v1",
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error)[:500],
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
