from datetime import datetime

from pydantic import BaseModel


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
    url: str
