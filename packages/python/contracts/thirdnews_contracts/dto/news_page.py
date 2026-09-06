from pydantic import BaseModel

from .news_item import NewsItem


class NewsPage(BaseModel):
    items: list[NewsItem]
    next_cursor: str | None = None
    total: int | None = None
