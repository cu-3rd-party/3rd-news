from collections.abc import Collection
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class UrlPolicy:
    allowed_hosts: frozenset[str] = frozenset()
    allowed_schemes: frozenset[str] = frozenset({"http", "https"})
    max_redirects: int = 3

    @classmethod
    def with_service_hosts(cls, hosts: Collection[str], *, max_redirects: int = 3) -> Self:
        return cls(
            allowed_hosts=frozenset(host.rstrip(".").lower() for host in hosts),
            max_redirects=max_redirects,
        )
