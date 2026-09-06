from typing import Any

from pydantic import BaseModel


class SelectionOut(BaseModel):
    team: str
    channel: str
    display_name: str | None = None
    slug: str
    added_at: str
    authors: str = "privileged"
    last_run: dict[str, Any] | None = None
