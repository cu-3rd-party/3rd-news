# Инструменты корпуса, таксономии и оценки

Инструменты запускаются из отдельного Python 3.14 проекта и принимают параметры только через `pydantic-settings`. Все HTTP соединения задаются атомарно через `MAIN_SCHEME`, `MAIN_HOST` и `MAIN_PORT`; учётные данные администратора читаются из `BOOTSTRAP_ADMIN_EMAIL` и `BOOTSTRAP_ADMIN_PASSWORD`.

```bash
uv sync --project tools --locked --all-groups
```

## Оценка классификаторов

Команда `uv run --project tools evaluation` выбирает действие через `EVAL_ACTION`: `run`, `compare`, `blind` или `kappa`. Пути и параметры задаются переменными `EVAL_DATA_PATH`, `EVAL_TAXONOMY_PATH`, `EVAL_CONTEXT_PATH`, `EVAL_OUTPUT_PATH`, `EVAL_RESULT_PATHS`, `EVAL_OTHER_PATH`, `EVAL_CLASSIFIER`, `EVAL_EXAMPLES`, `EVAL_K`, `EVAL_MODEL`, `EVAL_EMBEDDER` и порогами `EVAL_*_THRESHOLD`.

```bash
EVAL_ACTION=run EVAL_DATA_PATH=data/gold.jsonl EVAL_TAXONOMY_PATH=data/taxonomy.json EVAL_CLASSIFIER=regex EVAL_OUTPUT_PATH=results/regex.json uv run --project tools evaluation
EVAL_ACTION=compare EVAL_RESULT_PATHS='["results/regex.json"]' uv run --project tools evaluation
EVAL_ACTION=blind EVAL_DATA_PATH=data/gold.jsonl EVAL_TAXONOMY_PATH=data/taxonomy.json EVAL_OUTPUT_PATH=data/blind.csv uv run --project tools evaluation
EVAL_ACTION=kappa EVAL_DATA_PATH=data/gold.jsonl EVAL_TAXONOMY_PATH=data/taxonomy.json EVAL_OTHER_PATH=data/friend.csv uv run --project tools evaluation
```

Золотой набор содержит только ручные решения. Ось в `manual_facets` с пустым списком меток означает осознанно пустую разметку; отсутствующая ось не участвует в метрике. Выбор примеров исключает оцениваемую запись. Ответы модели кэшируются по хэшу запроса, а векторы — по хэшу текста.

## Корпус

Команда `uv run --project tools corpus` выбирает действие через `CORPUS_ACTION`: `copy-labels`, `gold`, `progress`, `reject-noise`, `release-facet` или `sample`. Изменения применяются только при `CORPUS_APPLY=true`. Остальные параметры имеют префикс `CORPUS_`, включая `CORPUS_THRESHOLD`, `CORPUS_SIZE`, `CORPUS_CAP`, `CORPUS_SEED`, `CORPUS_FACET` и `CORPUS_OUTPUT_PATH`.

## Таксономия

Команда `uv run --project tools taxonomy-apply` читает `TAXONOMY_PATH`. По умолчанию `TAXONOMY_DRY_RUN=true`; применение требует `TAXONOMY_DRY_RUN=false`. Удалённые из файла оси и значения выключаются только при `TAXONOMY_DEACTIVATE_EXTRA=true`.
