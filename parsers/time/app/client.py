"""Тонкий клиент TiMe (`time.cu.ru`).

TiMe — это Mattermost, поэтому всё общение идёт через его `/api/v4`. Клиент
умеет ровно то, что нужно парсеру: найти канал по человеческому имени из
адресной строки, вычитать посты и скачать вложения.

Авторизация — строка кук из браузера (`TIME_COOKIE`). Токен сессии лежит в
HttpOnly-куке `MMAUTHTOKEN`, из JS его не достать, поэтому куки снимаются
расширением (`tools/chrome-cookie-exporter` в репозитории 3rd-view) или
вручную через DevTools. Альтернатива — personal access token в `TIME_TOKEN`,
если админы TiMe их не запретили.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("3rdnews.parser.time")

#: Посты сервера («X присоединился к каналу») — не новости.
SYSTEM_POST_PREFIX = "system_"

#: Типы каналов Mattermost.
CHANNEL_PUBLIC = "O"
CHANNEL_PRIVATE = "P"
CHANNEL_DIRECT = "D"
CHANNEL_GROUP = "G"

#: Единственные типы, которые парсер вообще готов показывать и читать.
#: `D` и `G` — это личные и групповые переписки: у обычного аккаунта их
#: десятки, и попасть в новостную ленту они не должны никогда.
NEWS_CHANNEL_TYPES = frozenset({CHANNEL_PUBLIC, CHANNEL_PRIVATE})

#: Роли рядового участника канала. Всё, что сверх них, — признак того, что
#: человеку доверили писать: куратор, админ канала, роль кастомной схемы прав.
PLAIN_MEMBER_ROLES = frozenset({"channel_user", "channel_guest"})


def has_posting_privileges(roles: set[str]) -> bool:
    """Есть ли у автора права в канале сверх обычного участника."""

    return bool(set(roles) - PLAIN_MEMBER_ROLES)


class TimeAuthError(RuntimeError):
    """Куки протухли или их не хватает."""


class TimeApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChannelRef:
    """Канал, каким он записан в адресной строке TiMe."""

    team: str
    channel: str

    @property
    def slug(self) -> str:
        """Slug источника в 3rd-news."""

        return f"time-{self.team}-{self.channel}"

    @classmethod
    def parse(cls, value: str) -> "ChannelRef":
        """Принимает и полную ссылку, и короткое `команда/канал`.

        >>> ChannelRef.parse("https://time.cu.ru/tsentralnyy-universitet/channels/anonsy-tsu")
        ChannelRef(team='tsentralnyy-universitet', channel='anonsy-tsu')
        >>> ChannelRef.parse("tsentralnyy-universitet/anonsy-tsu")
        ChannelRef(team='tsentralnyy-universitet', channel='anonsy-tsu')
        """

        raw = value.strip()
        if not raw:
            raise ValueError("пустая ссылка на канал")

        if "://" in raw:
            raw = urlparse(raw).path

        parts = [part for part in raw.split("/") if part and part != "channels"]
        if len(parts) != 2:
            raise ValueError(
                f"не понимаю ссылку на канал {value!r}; "
                "ожидаю '<команда>/<канал>' или полный URL вида "
                "https://time.cu.ru/<команда>/channels/<канал>"
            )
        return cls(team=parts[0], channel=parts[1])


class TimeClient:
    def __init__(
        self,
        base_url: str = "https://time.cu.ru",
        cookie: str | None = None,
        csrf: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not cookie and not token:
            raise TimeAuthError("нужен либо TIME_COOKIE, либо TIME_TOKEN")

        self.base_url = base_url.rstrip("/")
        headers = {
            "accept": "application/json, text/plain, */*",
            # Mattermost отдаёт JSON и без него, но с этим заголовком он не
            # пытается редиректить на страницу логина.
            "x-requested-with": "XMLHttpRequest",
            "user-agent": "3rd-news-time-parser/0.1",
        }
        if cookie:
            headers["cookie"] = cookie
        if csrf:
            headers["x-csrf-token"] = csrf
        if token:
            headers["authorization"] = f"Bearer {token}"

        self._http = httpx.Client(
            base_url=f"{self.base_url}/api/v4",
            headers=headers,
            timeout=timeout,
            # Тесты подсовывают сюда MockTransport вместо живого TiMe.
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "TimeClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _get(self, path: str, **params) -> httpx.Response:
        response = self._http.get(path, params=params or None)
        if response.status_code in (401, 403):
            raise TimeAuthError(
                f"TiMe отвечает {response.status_code} на {path}. "
                "Скорее всего протухли куки — сними их заново."
            )
        if response.status_code >= 400:
            raise TimeApiError(f"{response.status_code} на {path}: {response.text[:300]}")
        return response

    # -- то, ради чего всё затевалось ------------------------------------- #

    def whoami(self) -> dict:
        """Проверка, что куки живые. Кидает TimeAuthError, если нет."""

        return self._get("/users/me").json()

    def resolve_channel(self, ref: ChannelRef) -> dict:
        """`команда/канал` из адресной строки → объект канала с его id."""

        team = self._get(f"/teams/name/{ref.team}").json()
        channel = self._get(f"/teams/{team['id']}/channels/name/{ref.channel}").json()
        # display_name — человеческое название, оно пойдёт в source_text.
        channel["team"] = team
        return channel

    # -- перечисление каналов --------------------------------------------- #

    def list_teams(self) -> list[dict]:
        """Команды, в которых состоит текущий пользователь."""

        return self._get("/users/me/teams").json()

    def list_public_channels(
        self, team_id: str, per_page: int = 200, max_pages: int = 50
    ) -> list[dict]:
        """Все публичные каналы команды.

        Их много (в ЦУ — больше полутора тысяч), поэтому ходим страницами до
        упора. `max_pages` — предохранитель от бесконечного цикла, а не
        ограничение выборки.
        """

        collected: list[dict] = []
        for page in range(max_pages):
            batch = self._get(
                f"/teams/{team_id}/channels", page=page, per_page=per_page
            ).json()
            collected.extend(batch)
            if len(batch) < per_page:
                break
        else:
            logger.warning(
                "перечисление каналов команды %s упёрлось в %d страниц", team_id, max_pages
            )
        return [c for c in collected if c.get("type") in NEWS_CHANNEL_TYPES]

    def channel_member_roles(self, channel_id: str, user_id: str) -> set[str]:
        """Роли пользователя в канале.

        В обычном канале это `channel_user`, у куратора добавляется
        `channel_admin`. В канале со своей схемой прав роли называются
        идентификаторами схемы — важно не само название, а то, что оно не
        сводится к правам рядового участника.
        """

        try:
            member = self._get(f"/channels/{channel_id}/members/{user_id}").json()
        except TimeApiError:
            # Автор мог выйти из канала — тогда прав у него точно нет.
            return set()
        return set((member.get("roles") or "").split())

    def list_joined_channels(self, team_id: str) -> list[dict]:
        """Каналы команды, в которых пользователь состоит.

        Личные и групповые переписки отфильтровываются здесь, а не у
        вызывающего: этот метод — единственная дверь, через которую они могли
        бы просочиться наружу.
        """

        channels = self._get(f"/users/me/teams/{team_id}/channels").json()
        return [c for c in channels if c.get("type") in NEWS_CHANNEL_TYPES]

    def fetch_posts(
        self, channel_id: str, per_page: int = 60, max_pages: int = 5
    ) -> list[dict]:
        """Свежие посты канала, от новых к старым.

        Mattermost отдаёт `order` (список id по времени) и `posts` (словарь).
        Порядок берём из `order`, иначе он теряется.
        """

        collected: list[dict] = []
        for page in range(max_pages):
            payload = self._get(
                f"/channels/{channel_id}/posts", page=page, per_page=per_page
            ).json()
            order = payload.get("order") or []
            posts = payload.get("posts") or {}
            collected.extend(posts[post_id] for post_id in order if post_id in posts)
            if len(order) < per_page:
                break
        return collected

    def download_file(self, file_id: str, max_bytes: int) -> bytes | None:
        """Скачивает вложение. Возвращает None, если оно больше лимита."""

        with self._http.stream("GET", f"/files/{file_id}") as response:
            if response.status_code >= 400:
                logger.warning("не смог скачать файл %s: %s", file_id, response.status_code)
                return None

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    logger.warning("файл %s больше лимита, пропускаю", file_id)
                    return None
                chunks.append(chunk)
        return b"".join(chunks)

    def user_display_name(self, user_id: str) -> str | None:
        """Имя автора поста — уходит в `extra`, чтоб не терять контекст."""

        try:
            user = self._get(f"/users/{user_id}").json()
        except (TimeApiError, TimeAuthError):
            return None
        full = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        return full or user.get("username")
