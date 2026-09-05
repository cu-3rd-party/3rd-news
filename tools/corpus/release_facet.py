"""Снимает ручные метки с оси, возвращая её автоматическому источнику.

Нужно для осей, которые заполняет источник (`program`): ручная метка
перебивает `default_labels` канала, и копия объявления в другом канале
разъезжается с оригиналом. Админка такие оси больше не даёт трогать, но
метки, проставленные раньше, надо убрать.

    python -m tools.corpus.release_facet program
    python -m tools.corpus.release_facet program --apply
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from tools.corpus.client import Admin, add_connection_args, credentials


def pinned(items: list[dict[str, Any]], facet: str) -> list[dict[str, Any]]:
    """Посты, у которых эта ось закреплена вручную."""

    return [item for item in items if facet in (item.get("manual_facets") or [])]


def describe(items: list[dict[str, Any]], facet: str) -> str:
    if not items:
        return f"ручных меток по оси «{facet}» нет"
    lines = [f"ручная метка по оси «{facet}» стоит у {len(items)} постов:", ""]
    for item in items:
        values = ", ".join((item.get("effective") or {}).get(facet, [])) or "—"
        title = " ".join((item.get("title") or "").split())[:50] or "(без заголовка)"
        lines.append(f"  {item['id'][:8]}  {item.get('source_key', ''):45.45}  {values:20.20}  {title}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_args(parser)
    parser.add_argument("facet", help="slug оси, например program")
    parser.add_argument("--apply", action="store_true", help="действительно снять метки")
    args = parser.parse_args(argv)

    creds = credentials(args)
    if creds is None:
        print("нужны --email/--password (или BOOTSTRAP_ADMIN_* в окружении)", file=sys.stderr)
        return 2

    with Admin.connect(args.base_url, *creds) as admin:
        items = pinned(list(admin.news()), args.facet)
        print(describe(items, args.facet))

        if not items or not args.apply:
            if items:
                print("\n(это только список; чтобы снять — --apply)")
            return 0

        for item in items:
            admin.client.put(
                f"/api/v1/admin/news/{item['id']}/labels",
                json={"labels": {}, "release_facets": [args.facet]},
            ).raise_for_status()
        print(f"\nснято меток: {len(items)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
