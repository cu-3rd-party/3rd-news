from pydantic import BaseModel

from .channel_out import ChannelOut


class ChannelPage(BaseModel):
    items: list[ChannelOut]
    total: int
    limit: int
    offset: int
