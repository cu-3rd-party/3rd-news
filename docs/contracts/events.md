# Events v2

JetStream переносит только ссылки на данные. `EventEnvelope` содержит
`event_id`, тип, время, aggregate id/version и metadata с correlation/causation.
В payload допустимы только JSON scalar IDs, версии и технические флаги.
Тексты новостей, секреты, presigned URLs, prompts и сырые AI payload запрещены.

Базовые типы: `submission.accepted.v2`, `classification.requested.v2` и
`search.projection.requested.v2`. Consumer загружает актуальное состояние из
PostgreSQL и использует `event_id` как inbox key.

JetStream subjects состоят из настроенного namespace и типа без дублирования
версии: `thirdnews.v2.submission.accepted`, `thirdnews.v2.classification.requested`
и `thirdnews.v2.search.projection.requested`. Поле `event_type` в envelope всегда
содержит полное имя типа с суффиксом `.v2`.
# Восстановление доставки

После исчерпания попыток outbox сохраняется в PostgreSQL и виден через
`GET /api/v1/admin/delivery`. JetStream consumer использует ограниченные повторы
с NAK backoff; перед подтверждением неуспешного сообщения он ждёт подтверждения
записи в отдельный persistent stream `<BROKER_STREAM>_DLQ`. Если эта запись
недоступна, исходное сообщение остаётся неподтверждённым. DLQ содержит только
идентификаторы, номер сообщения и код ошибки, без копии тела или HTTP-заголовков.

`GET /api/v1/admin/delivery/dead-letters?after=0&limit=100` возвращает историю
неуспешных доставок и cursor. `POST /api/v1/admin/delivery/{event_id}/replay`
ставит исходное outbox-событие на повтор после окна broker deduplication
(по умолчанию 601 секунда). Стабильный event ID сохраняет идемпотентность inbox.
Операция требует admin и журналируется. Невалидное сообщение без UUID event ID
не воспроизводится: исходных доверенных данных в PostgreSQL для него нет.
