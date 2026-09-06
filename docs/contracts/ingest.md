# Ingest v2

`CONTRACT_VERSION=2.0`. Парсер зависит только от `thirdnews_contracts` или от
JSON Schema в `contracts/http/`.

`POST /api/v1/news` принимает `NewsSubmission` и при фиксации оригинала и
outbox отвечает `202 IngestResult`. Идентичность задаётся парой `source` +
`external_id` либо `idempotency_key`. Повтор идентичного payload возвращает
прежний `submission_id` со статусом `duplicate`; иной payload с тем же ключом
даёт `409`. Совпадение текста не является дедупликацией.
Для одиночного запроса `idempotency_key` также можно передать только заголовком
`Idempotency-Key`. Обработчик объединяет transport-заголовок с телом до
валидации и вычисления payload digest, поэтому один и тот же ключ в заголовке
или поле тела имеет одинаковую семантику. Разные значения дают `409`.

`POST /api/v1/news/batch` принимает `{"items": [...]}` (1–200) и отвечает 202.
Каждый `BatchItemResult` имеет индекс и собственный статус `accepted`,
`duplicate`, `conflict` или `rejected`; ошибка элемента не откатывает успешные
элементы. Python alias `BatchSubmission = NewsSubmission | dict[str, Any]`
намеренно сохраняет сырой object: обработчик валидирует каждый member отдельно,
поэтому один повреждённый member не превращает весь batch в HTTP 422.
Строковые поля, ключи и значения вложенных JSON-объектов не принимают NUL и
другие управляющие символы Unicode, кроме структурных `TAB`, `LF` и `CR`.
Обычный многострочный Markdown поэтому сохраняется, а payload, который
PostgreSQL/JSONB не может безопасно записать или который способен подделать
строку журнала, отклоняется на границе контракта.

Закрытый файл проходит три шага: `POST /api/v1/uploads/presign` с именем,
content type, размером и SHA-256; PUT точных байтов по выданному URL и с
выданными заголовками; `POST /api/v1/uploads/complete`. Submission ссылается на
завершённый intent через `upload_intent_id`. Сервер повторно проверяет объект,
размер и digest, затем закрепляет неизменяемый объект.

API key передаётся как `X-API-Key: ...`. `Authorization: Bearer` зарезервирован
для подписанных Ed25519 JWT между сервисными узлами. Постоянный ключ не
передаётся в URL.

Machine schemas and the complete HTTP OpenAPI are exported with
`uv run --project tools --locked contracts-export`.
`make contracts` and `just contracts` compare those files with the current typed models
without changing files; CI performs the same drift check.


Unused upload reservations are limited per authenticated owner to 20 intents and
200 MB in total. Expired pending uploads are collected; completed but unconsumed
uploads expire after seven days. Attached objects remain protected by their DB
ownership, including archived news. A periodic collector removes old unreferenced
objects after a 24-hour grace period, covering crashes and fenced worker attempts.
The collector runs in the pipeline role and retries storage failures.

Production requires `FILE_PUBLIC_SCHEME=https` with a public `FILE_PUBLIC_HOST`; the production Compose
overlay derives it from the separate `UPLOAD_ADDRESS` DNS name. A random 32-byte
base64 raw-audit encryption key is mandatory in production for API and workers.
