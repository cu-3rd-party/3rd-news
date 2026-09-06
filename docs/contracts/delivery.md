# Delivery v2

Пользовательская лента доступна через `GET /api/v1/feed`, detail через
`GET /api/v1/news/{id}`, RSS через `GET /api/v1/rss.xml`. Все ручки, totals, facets,
snippets и media proxy применяют одну политику доступа. Кандидаты Meilisearch
перепроверяются в PostgreSQL. Если ограничение видимости ещё не подтверждено
поисковой проекцией, feed отвечает 503 и не выдаёт устаревшие агрегаты.

Вложения открываются только через авторизующий media proxy, включая HEAD и
Range. URL не содержит постоянного API key.


## Operator recovery

`GET /api/v1/admin/delivery` returns undelivered outbox identifiers, attempt
counts, scheduled times and safe error codes. `GET /api/v1/admin/delivery/dead-letters`
returns the durable failure history with `after`/`limit` pagination and a cursor.
Neither endpoint returns event bodies or news text.

`POST /api/v1/admin/delivery/{event_id}/replay` requires admin authorization and
CSRF for cookie authentication, records an audit entry, and returns 202 with
`available_at`. Replay waits 601 seconds to outlive the configured JetStream
600-second deduplication window. The canonical event identifier remains stable;
inbox checks prevent an already-applied event from applying twice. Operators can
also rebuild the search projection from PostgreSQL using `tools/ops/reindex.py`.

Consumers apply bounded retries with backoff, then persist identifier-only failure
records in a separate durable stream before acknowledging the original message.
If that publication fails, the original message remains eligible for delivery.
Outbox transport failures retry automatically with capped exponential backoff and no
terminal attempt limit. Permanent local validation failures are visibly quarantined
and available for explicit audited replay; safe structured warnings identify failures. Dead-letter
history is append-only and is not deleted by replay.
