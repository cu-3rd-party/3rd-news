from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Self

from ...interactor.interfaces.clients.admin import AdminClient
from .tool_http import ToolHttpClient

PAGE = 200


@dataclass
class Admin(AdminClient):
    client: ToolHttpClient

    @classmethod
    def connect(cls, base_url: str, email: str, password: str) -> Admin:
        client = ToolHttpClient(base_url=base_url, timeout=60.0)
        response = client.post("/api/v1/auth/token", json={"email": email, "password": password})
        response.raise_for_status()
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        return cls(client)

    def close(self) -> None:
        return None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def news(self, **params: Any) -> Iterator[dict[str, Any]]:
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
        if status not in {"published", "rejected"}:
            raise ValueError("status must be published or rejected")
        action = "publish" if status == "published" else "reject"
        self.client.post(f"/api/v1/admin/news/{news_id}/{action}").raise_for_status()

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
