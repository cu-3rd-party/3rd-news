"""Парсер каналов TiMe (`time.cu.ru`).

Читает объявления из канала мессенджера и шлёт их в 3rd-news. Состояние не
хранит: приём идемпотентен по `(source_key, external_id)`, а `external_id` —
это id поста в Mattermost, поэтому ленту можно перечитывать целиком сколько
угодно раз.

Вложения приходится скачивать самому и отправлять файлами: `/api/v4/files/...`
требует авторизации, и главный сервис по такой ссылке ничего не получит.

Запуск:

    NEWS_URL=http://localhost:8000 NEWS_API_KEY=tnk_... \
    TIME_COOKIE='MMAUTHTOKEN=...; MMUSERID=...' \
    TIME_CHANNELS=https://time.cu.ru/tsentralnyy-universitet/channels/anonsy-tsu \
        python -m app.main
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

from thirdnews_contracts import (
    AttachmentInput,
    AttachmentKind,
    IngestClient,
    IngestError,
    NewsSubmission,
)

from .client import (
    SYSTEM_POST_PREFIX,
    ChannelRef,
    TimeAuthError,
    TimeClient,
    has_posting_privileges,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("3rdnews.parser.time")

NEWS_URL = os.getenv("NEWS_URL", "http://main:8000")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

TIME_BASE_URL = os.getenv("TIME_BASE_URL", "https://time.cu.ru")
TIME_COOKIE = os.getenv("TIME_COOKIE", "")
TIME_CSRF = os.getenv("TIME_CSRF", "")
TIME_TOKEN = os.getenv("TIME_TOKEN", "")
#: Каналы через запятую: полный URL или `команда/канал`.
TIME_CHANNELS = os.getenv("TIME_CHANNELS", "")

POLL_INTERVAL_S = int(os.getenv("POLL_INTERVAL_S", "600"))
MAX_AGE_DAYS = int(os.getenv("MAX_AGE_DAYS", "30"))
POSTS_PER_PAGE = int(os.getenv("TIME_POSTS_PER_PAGE", "60"))
MAX_PAGES = int(os.getenv("TIME_MAX_PAGES", "5"))
#: Ответы в тредах — это обсуждение анонса, а не сам анонс.
INCLUDE_REPLIES = os.getenv("TIME_INCLUDE_REPLIES", "false").lower() == "true"
#: `privileged` — брать только посты авторов, которым в канале выданы права
#: сверх обычного участника: куратор, админ канала, роль кастомной схемы.
#: В чатах потоков это отсекает вопросы студентов, не потратив ни токена;
#: в новостных каналах не меняет ничего — там и так пишут только свои.
#: `all` — брать всё подряд.
AUTHORS = os.getenv("TIME_AUTHORS", "privileged").strip().lower()
DOWNLOAD_ATTACHMENTS = os.getenv("TIME_DOWNLOAD_ATTACHMENTS", "true").lower() == "true"
MAX_ATTACHMENT_BYTES = int(os.getenv("TIME_MAX_ATTACHMENT_BYTES", str(64 * 1024 * 1024)))

#: Заголовок вытаскиваем из первой строки, но только если она похожа на
#: заголовок, а не на начало абзаца.
MAX_TITLE_LEN = 150
#: Кастомные эмодзи вида `:cu-black-hat:`. Требуем букву в начале, иначе
#: под шаблон попадёт время «18:00:20».
_EMOJI_SHORTCODE = re.compile(r":[a-z][a-z0-9_+-]*:", re.IGNORECASE)
#: Инлайновая разметка: **жирный**, _курсив_, `код`.
_EMPHASIS = re.compile(r"[*_`~]+")
_LEADING_NOISE = re.compile(r"^[\s>#\-–—•·]+")
_EMPTY_MARKDOWN = re.compile(r"^[\s>#*_`~\-–—•·]*$")


# --------------------------------------------------------------------------- #
# Чистые функции: их гоняют тесты на настоящих постах из фикстуры
# --------------------------------------------------------------------------- #


def is_newsworthy(post: dict, include_replies: bool = INCLUDE_REPLIES) -> bool:
    """Стоит ли вообще тащить этот пост в новости.

    Пост без текста, но с картинкой — это нормальный анонс афишей, и он
    остаётся. Пустым (без текста и без файлов) считается только совсем
    мусорный пост.
    """

    if post.get("delete_at"):
        return False
    if str(post.get("type", "")).startswith(SYSTEM_POST_PREFIX):
        return False
    if not include_replies and post.get("root_id"):
        return False
    return bool(post_body(post).strip()) or bool(post_files(post))


def post_body(post: dict) -> str:
    """Текст поста в Markdown.

    Обычный пост — это `message`. Но объявления часто присылает бот или
    вебхук, и тогда текст лежит в `props.attachments` (это «message
    attachments» Mattermost, к файлам они отношения не имеют).
    """

    parts: list[str] = []
    message = (post.get("message") or "").strip()
    if message:
        parts.append(message)

    props = post.get("props") or {}
    for attachment in props.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        for field in ("pretext", "title", "text", "fallback"):
            value = (attachment.get(field) or "").strip()
            # fallback — это дубль text для клиентов без разметки, берём его
            # только если больше ничего нет.
            if value and value not in parts:
                parts.append(value)
                if field == "text":
                    break
    return "\n\n".join(parts).strip()


def guess_title(body: str) -> str | None:
    """Первая строка как заголовок — если она на него похожа.

    В мессенджере заголовков нет, но объявления почти всегда начинаются со
    строки-названия, обычно жирной и с эмодзи: `**Стартуем в новый учебный
    год** :cu-black-hat:`. Разметку и эмодзи снимаем, тело поста при этом
    остаётся нетронутым.

    Если текст в одну строку, заголовок не выдумываем: он просто
    продублировал бы тело.
    """

    lines = [line for line in body.splitlines() if not _EMPTY_MARKDOWN.match(line)]
    if len(lines) < 2:
        return None

    first = _EMOJI_SHORTCODE.sub(" ", lines[0])
    first = _EMPHASIS.sub("", first)
    first = _LEADING_NOISE.sub("", first)
    first = re.sub(r"\s+", " ", first).strip()
    # Заголовок не заканчивается запятой: это строка, которую автор продолжил
    # на следующей. Вопросительный и восклицательный знаки оставляем.
    first = first.rstrip(" ,;:—–-")

    if not first or len(first) > MAX_TITLE_LEN:
        return None
    return first


def attachment_kind(mime: str | None, extension: str | None) -> AttachmentKind:
    mime = (mime or "").lower()
    extension = (extension or "").lower().lstrip(".")
    if mime.startswith("image/") or extension in {"png", "jpg", "jpeg", "gif", "webp", "svg"}:
        return AttachmentKind.IMAGE
    if mime.startswith("video/") or extension in {"mp4", "mov", "avi", "mkv", "webm"}:
        return AttachmentKind.VIDEO
    if mime.startswith("audio/") or extension in {"mp3", "wav", "ogg", "m4a"}:
        return AttachmentKind.AUDIO
    if mime == "application/pdf" or extension == "pdf":
        return AttachmentKind.PDF
    return AttachmentKind.FILE


def post_files(post: dict) -> list[dict]:
    """Метаданные вложений поста."""

    metadata = post.get("metadata") or {}
    return [item for item in (metadata.get("files") or []) if isinstance(item, dict)]


def permalink(base_url: str, team: str, post_id: str) -> str:
    return f"{base_url.rstrip('/')}/{team}/pl/{post_id}"


def _from_ms(raw: object) -> datetime | None:
    """Время у Mattermost — миллисекунды epoch, ноль означает «не было»."""

    if not raw:
        return None
    return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)  # type: ignore[arg-type]


def created_at(post: dict) -> datetime | None:
    return _from_ms(post.get("create_at"))


def post_to_submission(
    post: dict,
    *,
    ref: ChannelRef,
    channel_title: str,
    base_url: str = TIME_BASE_URL,
    author: str | None = None,
) -> NewsSubmission | None:
    """Пост Mattermost → новость 3rd-news. None, если пост не новость."""

    if not is_newsworthy(post):
        return None

    body = post_body(post)
    published = created_at(post)

    extra: dict = {"parser": "time", "channel": ref.channel, "team": ref.team}
    if author:
        extra["author"] = author
    edited = _from_ms(post.get("edit_at"))
    if edited:
        extra["edited_at"] = edited.isoformat()

    return NewsSubmission(
        external_id=post["id"],
        source_key=ref.slug,
        title=guess_title(body),
        body_md=body,
        source_link=permalink(base_url, ref.team, post["id"]),
        source_text=f"{channel_title}, TiMe",
        published_at=published,
        lang="ru",
        attachments=[
            AttachmentInput(
                kind=attachment_kind(item.get("mime_type"), item.get("extension")),
                upload_name=f"file_{index}",
                filename=item.get("name"),
                mime=item.get("mime_type"),
            )
            for index, item in enumerate(post_files(post))
        ],
        extra=extra,
    )


# --------------------------------------------------------------------------- #
# Цикл
# --------------------------------------------------------------------------- #


def parse_channels(spec: str) -> list[ChannelRef]:
    refs: list[ChannelRef] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            refs.append(ChannelRef.parse(chunk))
        except ValueError as exc:
            logger.warning("%s", exc)
    return refs


def _collect_files(time_client: TimeClient, post: dict) -> dict[str, tuple[str, bytes, str]]:
    """Скачивает вложения поста для multipart-отправки."""

    uploads: dict[str, tuple[str, bytes, str]] = {}
    for index, item in enumerate(post_files(post)):
        file_id = item.get("id")
        if not file_id:
            continue
        if int(item.get("size") or 0) > MAX_ATTACHMENT_BYTES:
            logger.info("вложение %s слишком большое, пропускаю", item.get("name"))
            continue
        data = time_client.download_file(file_id, MAX_ATTACHMENT_BYTES)
        if data is None:
            continue
        uploads[f"file_{index}"] = (
            item.get("name") or file_id,
            data,
            item.get("mime_type") or "application/octet-stream",
        )
    return uploads


def poll_channel(
    time_client: TimeClient,
    news_client: IngestClient,
    ref: ChannelRef,
    *,
    max_age_days: int | None = None,
    max_pages: int | None = None,
    authors: str | None = None,
) -> tuple[int, int, int]:
    """Один проход по каналу. Возвращает (создано, дубликаты, пропущено).

    `max_age_days` и `max_pages` переопределяют настройки на один прогон —
    этим разово затягивают историю только что добавленного канала, не меняя
    поведение фонового опроса.
    """

    channel = time_client.resolve_channel(ref)
    channel_title = channel.get("display_name") or ref.channel
    posts = time_client.fetch_posts(
        channel["id"], POSTS_PER_PAGE, max_pages if max_pages is not None else MAX_PAGES
    )

    window = max_age_days if max_age_days is not None else MAX_AGE_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)
    created = duplicates = skipped = 0
    # Имя автора для extra — не путать с параметром `authors`, который
    # решает, чьи посты вообще брать.
    author_names: dict[str, str | None] = {}
    privileged: dict[str, bool] = {}

    def may_post(user_id: str) -> bool:
        """Доверено ли автору писать в этот канал.

        Кэшируется на проход: авторов единицы, а постов сотни.
        """

        if (authors if authors is not None else AUTHORS) != "privileged":
            return True
        if user_id not in privileged:
            privileged[user_id] = has_posting_privileges(
                time_client.channel_member_roles(channel["id"], user_id)
            )
        return privileged[user_id]

    for post in posts:
        published = created_at(post)
        if published and published < cutoff:
            skipped += 1
            continue

        user_id = post.get("user_id")
        if user_id and not may_post(user_id):
            # Вопрос студента в чате потока, а не объявление куратора.
            skipped += 1
            continue

        if user_id and user_id not in author_names:
            author_names[user_id] = time_client.user_display_name(user_id)

        submission = post_to_submission(
            post,
            ref=ref,
            channel_title=channel_title,
            base_url=time_client.base_url,
            author=author_names.get(user_id or ""),
        )
        if submission is None:
            skipped += 1
            continue

        uploads = (
            _collect_files(time_client, post)
            if DOWNLOAD_ATTACHMENTS and submission.attachments
            else {}
        )
        # Вложение, которое не удалось скачать, не должно оставить в новости
        # ссылку в никуда.
        submission.attachments = [
            item for item in submission.attachments if item.upload_name in uploads
        ]

        try:
            result = news_client.submit(submission, files=uploads or None)
        except IngestError:
            logger.exception("не смог отправить пост %s", post.get("id"))
            continue

        if result.status.value == "created":
            created += 1
        else:
            duplicates += 1

    return created, duplicates, skipped


def poll_once(time_client: TimeClient, news_client: IngestClient, refs: list[ChannelRef]) -> None:
    for ref in refs:
        try:
            created, duplicates, skipped = poll_channel(time_client, news_client, ref)
        except TimeAuthError as exc:
            logger.error("%s", exc)
            raise
        except Exception:  # noqa: BLE001 — один сломанный канал не стоит остальных
            logger.exception("канал %s не прочитался", ref.slug)
            continue
        logger.info(
            "%s: %d новых, %d уже были, %d пропущено",
            ref.slug,
            created,
            duplicates,
            skipped,
        )


def main() -> None:
    if not NEWS_API_KEY:
        raise SystemExit("нужен NEWS_API_KEY — выпусти в админке ключ с правом ingest")
    if not TIME_COOKIE and not TIME_TOKEN:
        raise SystemExit("нужен TIME_COOKIE (или TIME_TOKEN) — см. parsers/time/README.md")

    refs = parse_channels(TIME_CHANNELS)
    if not refs:
        raise SystemExit("TIME_CHANNELS пуст; ожидаю ссылки на каналы через запятую")

    news_client = IngestClient(NEWS_URL, NEWS_API_KEY)
    with TimeClient(
        base_url=TIME_BASE_URL, cookie=TIME_COOKIE or None,
        csrf=TIME_CSRF or None, token=TIME_TOKEN or None,
    ) as time_client:
        me = time_client.whoami()
        logger.info(
            "вошёл в TiMe как %s, каналов: %d, опрос раз в %dс",
            me.get("username"),
            len(refs),
            POLL_INTERVAL_S,
        )
        while True:
            poll_once(time_client, news_client, refs)
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
