"""Измеритель классификаторов: золотой набор → метрики по осям.

Работает без ядра и без базы. Входы лежат в `data/`: `gold.jsonl` из
`GET /api/v1/admin/news/export`, `taxonomy.json` из `GET /api/v1/admin/facets`,
`context.md` — текст базы знаний. Классификаторы импортируются по пути и
зовутся напрямую, как в tests/conftest.py.
"""
