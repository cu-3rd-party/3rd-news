"""Helper for classifier authors: turns a plain function into a compliant service.

    from thirdnews_contracts import ClassifyRequest, ProposedLabel
    from thirdnews_contracts.worker import build_classifier_app

    def classify(request: ClassifyRequest) -> list[ProposedLabel]:
        ...

    app = build_classifier_app(
        slug="my-classifier", name="My classifier", classify=classify, secret=SECRET
    )

`build_classifier_app` mounts `GET /health`, `GET /manifest` and `POST /classify`,
and verifies the HMAC signature when a secret is configured. Using it is optional
— any HTTP server that speaks the same JSON is a valid classifier.
"""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable, Sequence

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import ValidationError

from .classifier import (
    ClassifierManifest,
    ClassifyRequest,
    ClassifyResponse,
    ProposedLabel,
)
from .signing import verify_signature

ClassifyFn = Callable[
    [ClassifyRequest], Sequence[ProposedLabel] | Awaitable[Sequence[ProposedLabel]]
]


def build_classifier_app(
    *,
    slug: str,
    name: str,
    classify: ClassifyFn,
    secret: str | None = None,
    version: str = "0.1.0",
    facets: list[str] | None = None,
    description: str | None = None,
    supports_async: bool = False,
) -> FastAPI:
    manifest = ClassifierManifest(
        slug=slug,
        name=name,
        version=version,
        facets=facets or ["*"],
        supports_async=supports_async,
        description=description,
    )
    app = FastAPI(title=name, version=version)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "classifier": slug}

    @app.get("/manifest", response_model=ClassifierManifest)
    async def get_manifest() -> ClassifierManifest:
        return manifest

    @app.post("/classify", response_model=ClassifyResponse)
    async def do_classify(
        request: Request,
        x_3rdnews_signature: str | None = Header(default=None),
        x_3rdnews_timestamp: str | None = Header(default=None),
    ) -> ClassifyResponse:
        raw = await request.body()
        if secret and not verify_signature(secret, raw, x_3rdnews_signature, x_3rdnews_timestamp):
            raise HTTPException(status_code=401, detail="bad signature")
        try:
            payload = ClassifyRequest.model_validate_json(raw)
        except ValidationError as exc:
            # A malformed request is the caller's mistake, not a server fault.
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        result = classify(payload)
        if inspect.isawaitable(result):
            result = await result
        return ClassifyResponse(
            request_id=payload.request_id, classifier=slug, labels=list(result)
        )

    return app
