# Verification evidence

These files contain only synthetic-load measurements and container resource counters.
The two 20-item runs used concurrency 10 and excluded external classification by setting
`source.skip_classification=true`. All 40 items reached `published`. This small queue
baseline verifies multi-worker correctness; it does not establish production capacity,
linear scaling, classifier quality, peak memory, or an SLO. `resources.txt` is one snapshot,
not a peak-memory profile. The disposable QA PostgreSQL instance is also visible there.

Reproduce with `make pipeline-load` or `just pipeline-load`, using a
new `LOAD_RUN_ID` each time. Configuration uses the `LOAD_API_SCHEME`, `LOAD_API_HOST`,
`LOAD_API_PORT`, `LOAD_MODE`, `LOAD_COUNT`, `LOAD_CONCURRENCY`,
`LOAD_WORKER_REPLICAS`, `LOAD_TIMEOUT_SECONDS`, and authentication environment fields.

`compose-smoke.json` — полный успешный сценарий с реальными внешними
классификаторами, загрузкой и закрытой выдачей. `live-integration.txt` —
проверки настоящих NATS, Garage и Meilisearch, включая отказ первой DLQ-публикации.
Эти результаты не заменяют ручной браузерный прогон или оценку качества модели.
