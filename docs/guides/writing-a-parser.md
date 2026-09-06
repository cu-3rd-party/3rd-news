# External parser

Парсер — отдельный сервис в `services/parser-<name>` с собственными
`pyproject.toml`, `uv.lock`, `.venv`, Dockerfile и каталогами `lib/{core,domain,
dto,interactor,infra,handlers}`. Корневой `main.py` запускает Granian factory
`lib.app:create_app`; polling task создаётся и закрывается в lifespan.

Установите `thirdnews-contracts` из `packages/python/contracts` и используйте
асинхронный `IngestClient`. `NewsSubmission` требует `source + external_id` или
`idempotency_key`; endpoint всегда `/api/v1/news`. Приватные файлы сначала
передаются через `await client.upload(...)`, затем completed upload id уходит в
`AttachmentInput.upload_intent_id`.

Парсер ограничивает время ответа и объём скачивания. Настроенные внутренние
адреса допустимы только как явные сервисные адаптеры; произвольный URL из
submission не должен обходить проверки главного сервиса.
