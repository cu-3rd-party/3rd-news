import json
import logging
import threading
from dataclasses import asdict
from pathlib import Path

from ...domain.entities.run_result import RunResult
from ...domain.entities.selection import Selection
from ...interactor.interfaces.storage.selection import SelectionStorage

logger = logging.getLogger("thirdnews.parser.time")


class JsonSelectionStorage(SelectionStorage):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._selected: dict[str, Selection] = {}
        self._runs: dict[str, RunResult] = {}
        self._load()

    def selected(self) -> list[Selection]:
        with self._lock:
            return sorted(self._selected.values(), key=lambda selection: selection.key)

    def is_selected(self, team: str, channel: str) -> bool:
        with self._lock:
            return f"{team}/{channel}" in self._selected

    def runs(self) -> dict[str, RunResult]:
        with self._lock:
            return dict(self._runs)

    def add(self, selection: Selection) -> bool:
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
            self._selected = {selection.key: selection for selection in selections}
            self._runs = {key: value for key, value in self._runs.items() if key in self._selected}
            self._save()

    def record_run(self, team: str, channel: str, result: RunResult) -> None:
        with self._lock:
            self._runs[f"{team}/{channel}"] = result
            self._save()

    def set_authors(self, team: str, channel: str, authors: str) -> bool:
        with self._lock:
            selection = self._selected.get(f"{team}/{channel}")
            if selection is None:
                return False
            selection.authors = authors
            self._save()
            return True

    def set_display_name(self, team: str, channel: str, display_name: str) -> None:
        with self._lock:
            selection = self._selected.get(f"{team}/{channel}")
            if selection is None or selection.display_name == display_name:
                return
            selection.display_name = display_name
            self._save()

    def seed(self, selections: list[Selection]) -> None:
        with self._lock:
            if self._selected or not selections:
                return
            self.replace_all(selections)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError, OSError:
            logger.warning("не смог прочитать состояние, начинаю с пустого выбора")
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
            "selected": [asdict(selection) for selection in self._selected.values()],
            "runs": {key: asdict(value) for key, value in self._runs.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
