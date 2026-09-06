# thirdnews-contracts v2

Независимый пакет публичных контрактов 3rd-news: строгие Pydantic-модели,
асинхронный клиент ingest и Ed25519 JWT-подпись сообщений. Пакет не импортирует
главный сервис.

```bash
uv add ./packages/python/contracts
```

Парсер отправляет `NewsSubmission` в `POST /api/v1/news`. Для каждого элемента
нужны `source + external_id` либо `idempotency_key`; успешный приём возвращает
`202 Accepted`. Классификаторы реализуют `GET /manifest`, точные health-пути и
`POST /classify`, используя `ClassifyRequest` / `ClassifyResponse`.
Неуспешная попытка явно передаётся как `status=failed` со структурированным
`error`; такой ответ нельзя применять как пустой успешный набор labels.

Подпись создаёт `sign_message()` и проверяет `verify_message()`. JWT разрешает
только `Ed25519` и связывает issuer, audience, job, attempt, node, срок действия,
уникальный jti и SHA-256 точного тела.
