import asyncio

from fastapi import APIRouter
from thirdnews_contracts import CallbackGateway, ReplayStorage, build_classifier_router

from ..core.config import Settings
from ..domain.entities.classifier import IDENTITY
from ..interactor.use_cases.classify import classify


def create_router(
    settings: Settings,
    background: set[asyncio.Task[None]],
    callback_client: CallbackGateway | None,
    replay_storage: ReplayStorage,
) -> APIRouter:
    return build_classifier_router(
        slug=IDENTITY.slug,
        name=IDENTITY.name,
        node_id=settings.classifier_node_id,
        classify=classify,
        caller_public_key=settings.classifier_caller_public_key,
        expected_issuer=settings.classifier_expected_issuer,
        audience=settings.classifier_audience,
        version=IDENTITY.version,
        callback_client=callback_client,
        replay_storage=replay_storage,
        description=IDENTITY.description,
        background=background,
    )
