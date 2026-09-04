"""HTTP-интерфейс парсера TiMe: посмотреть каналы, выбрать, запустить.

Отдельная маленькая админка у самого парсера, а не ручки в главном сервисе:
про TiMe, команды и каналы знает только он, и ядро от этих понятий свободно.
Любой другой парсер вправе не иметь ничего похожего — контракт с 3rd-news
по-прежнему один, `POST /api/v1/ingest/news`.

Каналов в ЦУ больше полутора тысяч, поэтому список ищется, фильтруется и
сортируется по активности, а не отдаётся простыней.

Запуск: `uvicorn app.api:app --host 0.0.0.0 --port 8000`
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from thirdnews_contracts import IngestClient

from . import main as parser
from .client import ChannelRef, TimeAuthError, TimeClient
from .state import RunResult, Selection, Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("3rdnews.parser.time")

STATIC_DIR = Path(__file__).parent / "static"
STATE_PATH = Path(os.getenv("STATE_PATH", "/data/state.json"))
#: Если задан — все ручки, кроме /health, требуют `Authorization: Bearer ...`.
API_TOKEN = os.getenv("PARSER_API_TOKEN", "")
#: Список каналов почти не меняется, а его сбор — девять запросов к TiMe.
CHANNEL_CACHE_TTL_S = int(os.getenv("CHANNEL_CACHE_TTL_S", "300"))
#: Типичное окно активности, подсказывается в описании фильтра.
ACTIVE_WITHIN_DAYS = int(os.getenv("ACTIVE_WITHIN_DAYS", "90"))

#: Страницы, которые отдаются без токена: сам интерфейс его спрашивает у
#: пользователя, а данных в них нет.
OPEN_PATHS = frozenset({"/", "/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})

store = Store(STATE_PATH)
_poll_lock = threading.Lock()
_channel_cache: dict[str, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Модели ответов
# --------------------------------------------------------------------------- #


class TeamOut(BaseModel):
    id: str
    name: str
    display_name: str


class ChannelOut(BaseModel):
    id: str
    team: str
    name: str
    display_name: str
    purpose: str | None = None
    header: str | None = None
    type: str
    total_msg_count: int = 0
    last_post_at: datetime | None = None
    selected: bool = False
    #: Ссылка, как её видно в браузере.
    url: str


class ChannelPage(BaseModel):
    items: list[ChannelOut]
    total: int
    limit: int
    offset: int


class SelectionOut(BaseModel):
    team: str
    channel: str
    display_name: str | None = None
    slug: str
    added_at: str
    #: `privileged` — только авторы с правами в канале, `all` — все подряд.
    authors: str = "privileged"
    last_run: dict | None = None


class SelectIn(BaseModel):
    """Каналы можно указывать ссылкой или как `команда/канал`."""

    channels: list[str] = Field(min_length=1)


class PollOut(BaseModel):
    ran: int
    results: dict[str, dict]


# --------------------------------------------------------------------------- #
# Вспомогательное
# --------------------------------------------------------------------------- #


def build_client() -> TimeClient:
    if not parser.TIME_COOKIE and not parser.TIME_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="нет доступа к TiMe: задай TIME_COOKIE или TIME_TOKEN",
        )
    return TimeClient(
        base_url=parser.TIME_BASE_URL,
        cookie=parser.TIME_COOKIE or None,
        csrf=parser.TIME_CSRF or None,
        token=parser.TIME_TOKEN or None,
    )


def _fetch_channels(refresh: bool = False) -> list[dict]:
    """Все каналы всех команд пользователя, с кэшем."""

    with _cache_lock:
        cached = _channel_cache.get("all")
        if cached and not refresh and time.time() - cached[0] < CHANNEL_CACHE_TTL_S:
            return cached[1]

    collected: list[dict] = []
    with build_client() as time_client:
        for team in time_client.list_teams():
            joined = {c["id"] for c in time_client.list_joined_channels(team["id"])}
            for channel in time_client.list_public_channels(team["id"]):
                if channel.get("delete_at"):
                    continue
                channel["_team_name"] = team["name"]
                channel["_joined"] = channel["id"] in joined
                collected.append(channel)

    with _cache_lock:
        _channel_cache["all"] = (time.time(), collected)
    return collected


def _to_out(channel: dict) -> ChannelOut:
    team = channel["_team_name"]
    last_post = channel.get("last_post_at") or 0
    return ChannelOut(
        id=channel["id"],
        team=team,
        name=channel["name"],
        display_name=channel.get("display_name") or channel["name"],
        purpose=channel.get("purpose") or None,
        header=(channel.get("header") or None),
        type=channel.get("type", "O"),
        total_msg_count=channel.get("total_msg_count") or 0,
        last_post_at=(
            datetime.fromtimestamp(last_post / 1000, tz=timezone.utc) if last_post else None
        ),
        selected=store.is_selected(team, channel["name"]),
        url=f"{parser.TIME_BASE_URL.rstrip('/')}/{team}/channels/{channel['name']}",
    )


def _parse_ref(value: str) -> ChannelRef:
    try:
        return ChannelRef.parse(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# Опрос
# --------------------------------------------------------------------------- #


def run_poll(
    only: ChannelRef | None = None,
    max_age_days: int | None = None,
    max_pages: int | None = None,
) -> dict[str, dict]:
    """Один проход по выбранным каналам. Не пускает два прохода разом."""

    selections = store.selected()
    if only is not None:
        selections = [s for s in selections if s.key == f"{only.team}/{only.channel}"]
    if not selections:
        return {}

    if not parser.NEWS_API_KEY:
        raise HTTPException(status_code=503, detail="не задан NEWS_API_KEY")

    # Каналы из TIME_CHANNELS заведены одними слагами; название узнаём из
    # уже собранного списка, лишнего запроса в TiMe это не стоит.
    if any(s.display_name is None for s in selections):
        try:
            known = {(c["_team_name"], c["name"]): c for c in _fetch_channels()}
            for s in selections:
                channel = known.get((s.team, s.channel))
                if s.display_name is None and channel:
                    store.set_display_name(
                        s.team, s.channel, channel.get("display_name") or s.channel
                    )
        except Exception:  # noqa: BLE001 — косметика не должна ронять прогон
            logger.debug("не смог подставить названия каналов", exc_info=True)
        selections = store.selected() if only is None else selections

    results: dict[str, dict] = {}
    with _poll_lock:
        news = IngestClient(parser.NEWS_URL, parser.NEWS_API_KEY)
        with build_client() as time_client:
            for selection in selections:
                ref = ChannelRef(team=selection.team, channel=selection.channel)
                try:
                    created, duplicates, skipped = parser.poll_channel(
                        time_client,
                        news,
                        ref,
                        max_age_days=max_age_days,
                        max_pages=max_pages,
                        authors=selection.authors,
                    )
                    result = RunResult(
                        created=created, duplicates=duplicates, skipped=skipped
                    )
                except TimeAuthError as exc:
                    # Куки протухли — остальные каналы тоже не прочитаются.
                    logger.error("%s", exc)
                    store.record_run(selection.team, selection.channel, RunResult(error=str(exc)))
                    raise
                except Exception as exc:  # noqa: BLE001 — один канал не стоит остальных
                    logger.exception("канал %s не прочитался", selection.slug)
                    result = RunResult(error=str(exc)[:500])

                store.record_run(selection.team, selection.channel, result)
                results[selection.key] = {
                    "created": result.created,
                    "duplicates": result.duplicates,
                    "skipped": result.skipped,
                    "error": result.error,
                }
                logger.info(
                    "%s: %d новых, %d уже были, %d пропущено%s",
                    selection.slug,
                    result.created,
                    result.duplicates,
                    result.skipped,
                    f", ошибка: {result.error}" if result.error else "",
                )
    return results


def _background_poller() -> None:
    while True:
        time.sleep(parser.POLL_INTERVAL_S)
        try:
            run_poll()
        except Exception:  # noqa: BLE001 — фоновый цикл не должен умирать
            logger.exception("фоновый проход не удался")


# --------------------------------------------------------------------------- #
# Ручки
# --------------------------------------------------------------------------- #

router = APIRouter()


@router.get("/teams", response_model=list[TeamOut], summary="Команды в TiMe")
def get_teams() -> list[TeamOut]:
    with build_client() as time_client:
        return [
            TeamOut(id=t["id"], name=t["name"], display_name=t.get("display_name") or t["name"])
            for t in time_client.list_teams()
        ]


@router.get("/channels", response_model=ChannelPage, summary="Все каналы TiMe")
def get_channels(
    q: str | None = Query(default=None, description="Поиск по имени, названию и описанию"),
    team: str | None = None,
    only_selected: bool = False,
    only_joined: bool = Query(default=False, description="Только те, где я состою"),
    only_with_posts: bool = True,
    active_within_days: int | None = Query(
        default=None, description=f"По умолчанию без ограничения; типичное значение — {ACTIVE_WITHIN_DAYS}"
    ),
    sort: str = Query(default="activity", pattern="^(activity|messages|name)$"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    refresh: bool = Query(default=False, description="Обойти кэш и перечитать из TiMe"),
) -> ChannelPage:
    """Каналы, из которых можно выбирать. Личных переписок здесь нет никогда."""

    channels = _fetch_channels(refresh=refresh)

    if team:
        channels = [c for c in channels if c["_team_name"] == team]
    if only_joined:
        channels = [c for c in channels if c["_joined"]]
    if only_with_posts:
        channels = [c for c in channels if (c.get("total_msg_count") or 0) > 0]
    if active_within_days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=active_within_days)).timestamp() * 1000
        channels = [c for c in channels if (c.get("last_post_at") or 0) >= cutoff]
    if q:
        needle = q.casefold()
        channels = [
            c
            for c in channels
            if needle in c["name"].casefold()
            or needle in (c.get("display_name") or "").casefold()
            or needle in (c.get("purpose") or "").casefold()
        ]
    if only_selected:
        channels = [c for c in channels if store.is_selected(c["_team_name"], c["name"])]

    if sort == "name":
        channels.sort(key=lambda c: (c.get("display_name") or c["name"]).casefold())
    elif sort == "messages":
        channels.sort(key=lambda c: c.get("total_msg_count") or 0, reverse=True)
    else:
        channels.sort(key=lambda c: c.get("last_post_at") or 0, reverse=True)

    page = channels[offset : offset + limit]
    return ChannelPage(
        items=[_to_out(c) for c in page], total=len(channels), limit=limit, offset=offset
    )


@router.get("/channels/selected", response_model=list[SelectionOut], summary="Что парсим")
def get_selected() -> list[SelectionOut]:
    runs = store.runs()
    return [
        SelectionOut(
            team=s.team,
            channel=s.channel,
            display_name=s.display_name,
            slug=s.slug,
            added_at=s.added_at,
            authors=s.authors,
            last_run=(
                {
                    "created": runs[s.key].created,
                    "duplicates": runs[s.key].duplicates,
                    "skipped": runs[s.key].skipped,
                    "error": runs[s.key].error,
                    "finished_at": runs[s.key].finished_at,
                }
                if s.key in runs
                else None
            ),
        )
        for s in store.selected()
    ]


@router.post("/channels/selected", response_model=list[SelectionOut], summary="Добавить каналы")
def add_selected(payload: SelectIn) -> list[SelectionOut]:
    known = {(c["_team_name"], c["name"]): c for c in _fetch_channels()}
    for value in payload.channels:
        ref = _parse_ref(value)
        channel = known.get((ref.team, ref.channel))
        if channel is None:
            raise HTTPException(
                status_code=404,
                detail=f"канала {ref.team}/{ref.channel} нет среди доступных; "
                "проверь ссылку или обнови список с ?refresh=true",
            )
        store.add(
            Selection(
                team=ref.team,
                channel=ref.channel,
                display_name=channel.get("display_name") or ref.channel,
            )
        )
    return get_selected()


@router.put("/channels/selected", response_model=list[SelectionOut], summary="Заменить выбор")
def replace_selected(payload: SelectIn) -> list[SelectionOut]:
    known = {(c["_team_name"], c["name"]): c for c in _fetch_channels()}
    selections: list[Selection] = []
    for value in payload.channels:
        ref = _parse_ref(value)
        channel = known.get((ref.team, ref.channel))
        if channel is None:
            raise HTTPException(status_code=404, detail=f"канала {ref.team}/{ref.channel} нет")
        selections.append(
            Selection(
                team=ref.team,
                channel=ref.channel,
                display_name=channel.get("display_name") or ref.channel,
            )
        )
    store.replace_all(selections)
    return get_selected()


@router.delete("/channels/selected", status_code=204, response_model=None, summary="Убрать канал")
def remove_selected(channel: str = Query(description="Ссылка или `команда/канал`")) -> None:
    ref = _parse_ref(channel)
    if not store.remove(ref.team, ref.channel):
        raise HTTPException(status_code=404, detail="этот канал и так не выбран")


@router.patch(
    "/channels/selected",
    response_model=list[SelectionOut],
    summary="Кого считать автором новостей в канале",
)
def set_authors(
    channel: str = Query(description="Ссылка или `команда/канал`"),
    authors: str = Query(pattern="^(privileged|all)$"),
) -> list[SelectionOut]:
    """Настройка на канал, потому что каналы устроены по-разному.

    В чатах потоков объявления пишут кураторы с правами админа, и `privileged`
    отсекает вопросы студентов. Но есть новостные каналы, где публикует
    обычный участник, — там тот же режим выкосил бы почти все анонсы.
    """

    ref = _parse_ref(channel)
    if not store.set_authors(ref.team, ref.channel, authors):
        raise HTTPException(status_code=404, detail="этот канал не выбран")
    return get_selected()


@router.post("/poll", response_model=PollOut, summary="Прогнать сейчас")
def poll_now(
    channel: str | None = Query(default=None, description="Только этот канал"),
    max_age_days: int | None = Query(
        default=None,
        ge=1,
        description="Разово расширить окно: так затягивают историю только что "
        "добавленного канала, не меняя фоновый опрос",
    ),
    max_pages: int | None = Query(default=None, ge=1, le=100),
) -> PollOut:
    only = _parse_ref(channel) if channel else None
    results = run_poll(only, max_age_days=max_age_days, max_pages=max_pages)
    return PollOut(ran=len(results), results=results)


@router.get("/status", summary="Состояние парсера")
def status() -> dict:
    runs = store.runs()
    return {
        "time_base_url": parser.TIME_BASE_URL,
        "authorized": bool(parser.TIME_COOKIE or parser.TIME_TOKEN),
        "news_url": parser.NEWS_URL,
        "news_key_configured": bool(parser.NEWS_API_KEY),
        "poll_interval_s": parser.POLL_INTERVAL_S,
        "selected": len(store.selected()),
        "last_runs": {
            key: {
                "created": r.created,
                "duplicates": r.duplicates,
                "skipped": r.skipped,
                "error": r.error,
                "finished_at": r.finished_at,
            }
            for key, r in runs.items()
        },
    }


# --------------------------------------------------------------------------- #
# Приложение
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    seeds = [
        Selection(team=ref.team, channel=ref.channel)
        for ref in parser.parse_channels(parser.TIME_CHANNELS)
    ]
    store.seed(seeds)
    threading.Thread(target=_background_poller, daemon=True, name="time-poller").start()
    logger.info(
        "парсер поднят: выбрано каналов %d, опрос раз в %dс",
        len(store.selected()),
        parser.POLL_INTERVAL_S,
    )
    yield


app = FastAPI(
    title="3rd-news · парсер TiMe",
    version="0.2.0",
    summary="Выбор каналов мессенджера ЦУ и выгрузка их в 3rd-news",
    lifespan=lifespan,
)


@app.middleware("http")
async def require_token(request: Request, call_next):
    """Простая защита: список каналов рабочего мессенджера — не для всех."""

    if API_TOKEN and request.url.path not in OPEN_PATHS:
        header = request.headers.get("authorization", "")
        if header.removeprefix("Bearer ").strip() != API_TOKEN:
            return JSONResponse({"detail": "нужен Authorization: Bearer <PARSER_API_TOKEN>"}, 401)
    return await call_next(request)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Страница выбора каналов."""

    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "parser-time"}


app.include_router(router)
