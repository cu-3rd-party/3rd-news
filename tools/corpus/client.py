"""Тонкий клиент админского API — общий для скриптов подготовки корпуса.

Ничего не кэширует и не умничает: логин, постраничное чтение ленты и три
операции записи, которые нужны при подготовке золотого набора.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

DEFAULT_BASE_URL = os.getenv("MAIN_BASE_URL", "http://127.0.0.1:8000")
#: Максимум, который принимает `list_news`.
PAGE = 200


@dataclass
class Admin:
    client: httpx.Client

    @classmethod
    def connect(cls, base_url: str, email: str, password: str) -> "Admin":
        client = httpx.Client(base_url=base_url, timeout=60.0)
        response = client.post("/api/v1/auth/token", json={"email": email, "password": password})
        response.raise_for_status()
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        return cls(client)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Admin":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def news(self, **params: Any) -> Iterator[dict[str, Any]]:
        """Вся выборка постранично: у ручки жёсткий потолок в 200 штук."""

        offset = 0
        while True:
            query = {**params, "limit": PAGE, "offset": offset}
            response = self.client.get("/api/v1/admin/news", params=query)
            response.raise_for_status()
            page = response.json()
            items = page["items"]
            yield from items
            offset += len(items)
            if not items or offset >= page["total"]:
                return

    def set_status(self, news_id: str, status: str) -> None:
        self.client.post(
            f"/api/v1/admin/news/{news_id}/status", json={"status": status}
        ).raise_for_status()

    def set_labels(self, news_id: str, labels: dict[str, list[str]]) -> None:
        self.client.put(
            f"/api/v1/admin/news/{news_id}/labels",
            json={"labels": labels, "release_facets": []},
        ).raise_for_status()

    def set_gold(self, ids: list[str], is_gold: bool = True) -> int:
        response = self.client.post(
            "/api/v1/admin/news/gold", json={"ids": ids, "is_gold": is_gold}
        )
        response.raise_for_status()
        return int(response.json()["updated"])


def credentials(args: Any) -> tuple[str, str] | None:
    email = args.email or os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    password = args.password or os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        return None
    return email, password


def add_connection_args(parser: Any) -> None:
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None)
