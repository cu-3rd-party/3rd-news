from dataclasses import dataclass
from typing import Self
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class ChannelRef:
    team: str
    channel: str

    @property
    def slug(self) -> str:
        return f"time-{self.team}-{self.channel}"

    @classmethod
    def parse(cls, value: str) -> Self:
        raw = value.strip()
        if not raw:
            raise ValueError("пустая ссылка на канал")
        if "://" in raw:
            raw = urlparse(raw).path
        parts = [part for part in raw.split("/") if part and part != "channels"]
        if len(parts) != 2:
            raise ValueError("ожидаю '<команда>/<канал>' или полный URL TiMe")
        return cls(team=parts[0], channel=parts[1])
