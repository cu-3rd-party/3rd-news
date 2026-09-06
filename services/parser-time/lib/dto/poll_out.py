from typing import Any

from pydantic import BaseModel


class PollOut(BaseModel):
    ran: int
    results: dict[str, dict[str, Any]]
