from dataclasses import dataclass, field
from typing import Any

from .patch import Patch


@dataclass
class Plan:
    create_facets: list[dict[str, Any]] = field(default_factory=list)
    patch_facets: list[Patch] = field(default_factory=list)
    create_values: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    patch_values: list[Patch] = field(default_factory=list)
    patch_sources: list[Patch] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    deactivate_facets: list[Patch] = field(default_factory=list)
    deactivate_values: list[Patch] = field(default_factory=list)

    def has_work(self, deactivate: bool = False) -> bool:
        work = bool(
            self.create_facets
            or self.patch_facets
            or self.create_values
            or self.patch_values
            or self.patch_sources
        )
        if deactivate:
            work = work or bool(self.deactivate_facets or self.deactivate_values)
        return work
