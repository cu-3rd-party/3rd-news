import asyncio

from fastapi import APIRouter
from thirdnews_contracts import (
    CallbackGateway,
    ClassifyRequest,
    DeferredClassification,
    ReplayStorage,
    build_classifier_router,
)

from ..core.config import Settings
from ..domain.entities.classifier import IDENTITY
from ..interactor.use_cases.ai_classification import AIClassification


def create_router(
    settings: Settings,
    classifier: AIClassification,
    background: set[asyncio.Task[None]],
    callback_client: CallbackGateway | None,
    replay_storage: ReplayStorage,
) -> APIRouter:
    def dispatch(request: ClassifyRequest):
        if settings.classifier_async_callbacks:
            return DeferredClassification(classifier.execute(request))
        return classifier.execute(request)

    return build_classifier_router(
        slug=IDENTITY.slug,
        name=IDENTITY.name,
        node_id=settings.classifier_node_id,
        classify=dispatch,
        caller_public_key=settings.classifier_caller_public_key,
        expected_issuer=settings.classifier_expected_issuer,
        audience=settings.classifier_audience,
        version=IDENTITY.version,
        callback_client=callback_client,
        replay_storage=replay_storage,
        description=IDENTITY.description,
        supports_async=settings.classifier_async_callbacks,
        background=background,
    )
