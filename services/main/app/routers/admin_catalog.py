"""Sources, API keys, classifier registrations, users, stats."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from slugify import slugify
from sqlalchemy import func, select

from .. import audit, knowledge
from ..config import settings
from ..deps import AdminPrincipal, DbSession, EditorPrincipal
from ..models import (
    ApiKey,
    ClassificationJob,
    Classifier,
    News,
    Source,
    User,
)
from ..schemas import (
    ApiKeyCreated,
    ContextIn,
    ContextOut,
    ApiKeyIn,
    ApiKeyOut,
    ClassifierIn,
    ClassifierOut,
    ClassifierProbe,
    SourceIn,
    SourceOut,
    StatsOut,
    UserIn,
    UserOut,
)
from ..security import generate_api_key, hash_password

router = APIRouter(prefix="/api/v1/admin", tags=["admin:catalog"])

VALID_SCOPES = {"read", "ingest", "editor", "admin"}


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #


def _source_out(source: Source) -> SourceOut:
    return SourceOut(
        id=str(source.id),
        slug=source.slug,
        title=source.title,
        kind=source.kind,
        url=source.url,
        description=source.description,
        is_active=source.is_active,
        default_labels=source.default_labels or {},
        skip_classification=source.skip_classification,
        last_ingest_at=source.last_ingest_at,
    )


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(session: DbSession, principal: EditorPrincipal) -> list[SourceOut]:
    del principal
    sources = (await session.execute(select(Source).order_by(Source.title))).scalars().all()
    return [_source_out(source) for source in sources]


@router.post("/sources", response_model=SourceOut, status_code=201)
async def create_source(
    payload: SourceIn, session: DbSession, principal: AdminPrincipal
) -> SourceOut:
    slug = slugify(payload.slug or payload.title)[:120]
    if not slug:
        raise HTTPException(status_code=422, detail="cannot derive a slug from the title")
    if (await session.execute(select(Source).where(Source.slug == slug))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"source {slug!r} already exists")

    source = Source(
        slug=slug,
        title=payload.title,
        kind=payload.kind,
        url=payload.url,
        description=payload.description,
        is_active=payload.is_active,
        default_labels=payload.default_labels,
        skip_classification=payload.skip_classification,
    )
    session.add(source)
    await session.flush()
    await audit.log(session, principal, "create", "source", str(source.id), {"slug": slug})
    await session.commit()
    return _source_out(source)


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: str, payload: SourceIn, session: DbSession, principal: AdminPrincipal
) -> SourceOut:
    source = (
        await session.execute(select(Source).where(Source.id == source_id))
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")

    source.title = payload.title
    source.kind = payload.kind
    source.url = payload.url
    source.description = payload.description
    source.is_active = payload.is_active
    source.default_labels = payload.default_labels
    source.skip_classification = payload.skip_classification
    if payload.slug:
        source.slug = slugify(payload.slug)[:120]

    await audit.log(session, principal, "update", "source", source_id, {"slug": source.slug})
    await session.commit()
    return _source_out(source)


# --------------------------------------------------------------------------- #
# API keys
# --------------------------------------------------------------------------- #


def _key_out(key: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=str(key.id),
        name=key.name,
        prefix=key.prefix,
        scopes=list(key.scopes or []),
        source_id=str(key.source_id) if key.source_id else None,
        filter_preset=key.filter_preset or {},
        is_active=key.is_active,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
    )


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(session: DbSession, principal: AdminPrincipal) -> list[ApiKeyOut]:
    del principal
    keys = (await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))).scalars().all()
    return [_key_out(key) for key in keys]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    payload: ApiKeyIn, session: DbSession, principal: AdminPrincipal
) -> ApiKeyCreated:
    unknown = set(payload.scopes) - VALID_SCOPES
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown scopes: {', '.join(sorted(unknown))}")

    secret, prefix, key_hash = generate_api_key()
    key = ApiKey(
        name=payload.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=payload.scopes,
        source_id=payload.source_id,
        filter_preset=payload.filter_preset,
        expires_at=payload.expires_at,
    )
    session.add(key)
    await session.flush()
    await audit.log(
        session, principal, "create", "api_key", str(key.id), {"name": key.name, "scopes": key.scopes}
    )
    await session.commit()
    # The only time the caller ever sees the full key.
    return ApiKeyCreated(key=_key_out(key), secret=secret)


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyOut)
async def revoke_api_key(key_id: str, session: DbSession, principal: AdminPrincipal) -> ApiKeyOut:
    key = (await session.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="api key not found")
    key.is_active = False
    await audit.log(session, principal, "revoke", "api_key", key_id, {"name": key.name})
    await session.commit()
    return _key_out(key)


# --------------------------------------------------------------------------- #
# Classifiers
# --------------------------------------------------------------------------- #


def _classifier_out(classifier: Classifier) -> ClassifierOut:
    return ClassifierOut(
        id=str(classifier.id),
        slug=classifier.slug,
        name=classifier.name,
        base_url=classifier.base_url,
        facets=list(classifier.facets or []),
        config=classifier.config or {},
        is_active=classifier.is_active,
        priority=classifier.priority,
        min_confidence=classifier.min_confidence,
        auto_apply=classifier.auto_apply,
        timeout_s=classifier.timeout_s,
        last_ok_at=classifier.last_ok_at,
        last_error=classifier.last_error,
        last_error_at=classifier.last_error_at,
        has_secret=bool(classifier.secret),
    )


@router.get("/classifiers", response_model=list[ClassifierOut])
async def list_classifiers(session: DbSession, principal: AdminPrincipal) -> list[ClassifierOut]:
    del principal
    rows = (
        (await session.execute(select(Classifier).order_by(Classifier.priority.desc())))
        .scalars()
        .all()
    )
    return [_classifier_out(row) for row in rows]


@router.post("/classifiers", response_model=ClassifierOut, status_code=201)
async def register_classifier(
    payload: ClassifierIn, session: DbSession, principal: AdminPrincipal
) -> ClassifierOut:
    slug = slugify(payload.slug or payload.name)[:120]
    if not slug:
        raise HTTPException(status_code=422, detail="cannot derive a slug from the name")
    if (
        await session.execute(select(Classifier).where(Classifier.slug == slug))
    ).scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"classifier {slug!r} already exists")

    classifier = Classifier(
        slug=slug,
        name=payload.name,
        base_url=payload.base_url.rstrip("/"),
        secret=payload.secret,
        facets=payload.facets,
        config=payload.config,
        is_active=payload.is_active,
        priority=payload.priority,
        min_confidence=payload.min_confidence,
        auto_apply=payload.auto_apply,
        timeout_s=payload.timeout_s,
    )
    session.add(classifier)
    await session.flush()
    await audit.log(
        session, principal, "create", "classifier", str(classifier.id), {"slug": slug}
    )
    await session.commit()
    return _classifier_out(classifier)


@router.patch("/classifiers/{classifier_id}", response_model=ClassifierOut)
async def update_classifier(
    classifier_id: str, payload: ClassifierIn, session: DbSession, principal: AdminPrincipal
) -> ClassifierOut:
    classifier = (
        await session.execute(select(Classifier).where(Classifier.id == classifier_id))
    ).scalar_one_or_none()
    if classifier is None:
        raise HTTPException(status_code=404, detail="classifier not found")

    classifier.name = payload.name
    classifier.base_url = payload.base_url.rstrip("/")
    classifier.facets = payload.facets
    classifier.config = payload.config
    classifier.is_active = payload.is_active
    classifier.priority = payload.priority
    classifier.min_confidence = payload.min_confidence
    classifier.auto_apply = payload.auto_apply
    classifier.timeout_s = payload.timeout_s
    # An omitted secret keeps the stored one; sending "" clears it.
    if payload.secret is not None:
        classifier.secret = payload.secret or None

    await audit.log(
        session, principal, "update", "classifier", classifier_id, {"slug": classifier.slug}
    )
    await session.commit()
    return _classifier_out(classifier)


@router.delete("/classifiers/{classifier_id}", status_code=204, response_model=None)
async def delete_classifier(
    classifier_id: str, session: DbSession, principal: AdminPrincipal
) -> None:
    classifier = (
        await session.execute(select(Classifier).where(Classifier.id == classifier_id))
    ).scalar_one_or_none()
    if classifier is None:
        raise HTTPException(status_code=404, detail="classifier not found")
    await audit.log(
        session, principal, "delete", "classifier", classifier_id, {"slug": classifier.slug}
    )
    await session.delete(classifier)
    await session.commit()


@router.post("/classifiers/{classifier_id}/probe", response_model=ClassifierProbe)
async def probe_classifier(
    classifier_id: str, session: DbSession, principal: AdminPrincipal
) -> ClassifierProbe:
    """Fetch the service's manifest, so a wrong URL is caught at setup time."""

    del principal
    classifier = (
        await session.execute(select(Classifier).where(Classifier.id == classifier_id))
    ).scalar_one_or_none()
    if classifier is None:
        raise HTTPException(status_code=404, detail="classifier not found")

    try:
        async with httpx.AsyncClient(timeout=classifier.timeout_s) as http:
            response = await http.get(f"{classifier.base_url}/manifest")
            response.raise_for_status()
            return ClassifierProbe(ok=True, manifest=response.json())
    except httpx.HTTPError as exc:
        return ClassifierProbe(ok=False, error=str(exc))


# --------------------------------------------------------------------------- #
# Users and stats
# --------------------------------------------------------------------------- #


@router.get("/users", response_model=list[UserOut])
async def list_users(session: DbSession, principal: AdminPrincipal) -> list[UserOut]:
    del principal
    users = (await session.execute(select(User).order_by(User.email))).scalars().all()
    return [
        UserOut(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )
        for user in users
    ]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserIn, session: DbSession, principal: AdminPrincipal) -> UserOut:
    if payload.role not in {"admin", "editor", "reader"}:
        raise HTTPException(status_code=422, detail="role must be admin, editor or reader")
    email = payload.email.lower()
    if (await session.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="user already exists")

    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password) if payload.password else None,
        role=payload.role,
        is_active=payload.is_active,
    )
    session.add(user)
    await session.flush()
    await audit.log(session, principal, "create", "user", str(user.id), {"email": email})
    await session.commit()
    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


@router.get("/stats", response_model=StatsOut)
async def stats(session: DbSession, principal: EditorPrincipal) -> StatsOut:
    del principal
    by_status = {
        status: count
        for status, count in (
            await session.execute(select(News.status, func.count()).group_by(News.status))
        ).all()
    }
    pending_jobs = (
        await session.execute(
            select(func.count())
            .select_from(ClassificationJob)
            .where(ClassificationJob.status.in_(["queued", "running", "awaiting_callback"]))
        )
    ).scalar_one()
    sources = (await session.execute(select(func.count()).select_from(Source))).scalar_one()
    classifiers_active = (
        await session.execute(
            select(func.count()).select_from(Classifier).where(Classifier.is_active.is_(True))
        )
    ).scalar_one()

    return StatsOut(
        news_total=sum(by_status.values()),
        by_status=by_status,
        pending_jobs=pending_jobs,
        sources=sources,
        classifiers_active=classifiers_active,
    )


# --------------------------------------------------------------------------- #
# База знаний классификаторов
# --------------------------------------------------------------------------- #


@router.get("/classification-context", response_model=ContextOut)
async def get_classification_context(
    session: DbSession, principal: EditorPrincipal
) -> ContextOut:
    """Что классификаторы знают об организации и на каких примерах учатся."""

    del principal
    examples = await knowledge.collect_examples(session)
    return ContextOut(
        text=await knowledge.get_context(session) or "",
        example_count=len(examples),
        examples_configured=settings.classifier_example_count,
    )


@router.put("/classification-context", response_model=ContextOut)
async def set_classification_context(
    payload: ContextIn, session: DbSession, principal: AdminPrincipal
) -> ContextOut:
    await knowledge.set_context(session, payload.text)
    await audit.log(
        session, principal, "update", "setting", knowledge.CONTEXT_KEY,
        {"length": len(payload.text)},
    )
    await session.commit()
    return await get_classification_context(session, principal)
