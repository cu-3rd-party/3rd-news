"""Какие каналы выбраны для парсинга, и что было в последний прогон.

Состояние живёт у самого парсера, а не в главном сервисе: тот про TiMe и его
каналы ничего не знает и знать не должен — иначе каждый новый парсер тянул бы
свои понятия в общее ядро.

Файл, а не база: выбор — это десяток строк, которые меняются вручную. Запись
атомарная (во временный файл и `replace`), чтобы прерванный процесс не оставил
после себя обрезанный JSON.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("3rdnews.parser.time")


@dataclass
class Selection:
    """Один выбранный канал."""

    team: str
    channel: str
    display_name: str | None = None
    #: `privileged` — только авторы с правами в канале, `all` — все подряд.
    #: Настройка на канал, а не общая: в чатах потоков объявления пишут
    #: кураторы с `channel_admin`, а в некоторых новостных каналах — обычный
    #: участник, и там фильтр выкосил бы почти всё.
    authors: str = "privileged"
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def slug(self) -> str:
        return f"time-{self.team}-{self.channel}"

    @property
    def key(self) -> str:
        return f"{self.team}/{self.channel}"


@dataclass
class RunResult:
    """Итог последнего прохода по каналу."""

    created: int = 0
    duplicates: int = 0
    skipped: int = 0
    error: str | None = None
    finished_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Store:
    """Потокобезопасное хранилище выбора и результатов прогонов."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._selected: dict[str, Selection] = {}
        self._runs: dict[str, RunResult] = {}
        self._load()

    # -- чтение ------------------------------------------------------------ #

    def selected(self) -> list[Selection]:
        with self._lock:
            return sorted(self._selected.values(), key=lambda s: s.key)

    def is_selected(self, team: str, channel: str) -> bool:
        with self._lock:
            return f"{team}/{channel}" in self._selected

    def runs(self) -> dict[str, RunResult]:
        with self._lock:
            return dict(self._runs)

    # -- изменение --------------------------------------------------------- #

    def add(self, selection: Selection) -> bool:
        """True, если канал добавлен, False — если уже был выбран."""

        with self._lock:
            if selection.key in self._selected:
                return False
            self._selected[selection.key] = selection
            self._save()
            return True

    def remove(self, team: str, channel: str) -> bool:
        with self._lock:
            removed = self._selected.pop(f"{team}/{channel}", None)
            self._runs.pop(f"{team}/{channel}", None)
            if removed is not None:
                self._save()
            return removed is not None

    def replace_all(self, selections: list[Selection]) -> None:
        with self._lock:
            self._selected = {s.key: s for s in selections}
            self._runs = {k: v for k, v in self._runs.items() if k in self._selected}
            self._save()

    def record_run(self, team: str, channel: str, result: RunResult) -> None:
        with self._lock:
            self._runs[f"{team}/{channel}"] = result
            self._save()

    def set_authors(self, team: str, channel: str, authors: str) -> bool:
        """Сменить режим отбора авторов для одного канала."""

        with self._lock:
            selection = self._selected.get(f"{team}/{channel}")
            if selection is None:
                return False
            selection.authors = authors
            self._save()
            return True

    def set_display_name(self, team: str, channel: str, display_name: str) -> None:
        """Подставить человеческое название.

        Каналы из `TIME_CHANNELS` приходят одними слагами, без названия —
        оно узнаётся только при первом обращении к TiMe.
        """

        with self._lock:
            selection = self._selected.get(f"{team}/{channel}")
            if selection is None or selection.display_name == display_name:
                return
            selection.display_name = display_name
            self._save()

    def seed(self, selections: list[Selection]) -> None:
        """Первичное заполнение из TIME_CHANNELS — только если выбор пуст.

        Существующий выбор переменной окружения не перетирается: иначе
        рестарт контейнера откатывал бы всё, что настроили руками.
        """

        with self._lock:
            if self._selected or not selections:
                return
            logger.info("первичный выбор из TIME_CHANNELS: %d канал(ов)", len(selections))
            self.replace_all(selections)

    # -- диск -------------------------------------------------------------- #

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("не смог прочитать %s (%s), начинаю с пустого выбора", self.path, exc)
            return

        for item in raw.get("selected", []):
            try:
                selection = Selection(**item)
            except TypeError:
                continue
            self._selected[selection.key] = selection
        for key, item in (raw.get("runs") or {}).items():
            try:
                self._runs[key] = RunResult(**item)
            except TypeError:
                continue

    def _save(self) -> None:
        payload = {
            "selected": [asdict(s) for s in self._selected.values()],
            "runs": {k: asdict(v) for k, v in self._runs.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
