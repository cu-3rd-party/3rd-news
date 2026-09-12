# External parser

Парсер — отдельный сервис в `services/parser-<name>` с собственными
`pyproject.toml`, `uv.lock`, `.venv`, Dockerfile и каталогами `lib/{core,domain,
dto,interactor,infra,handlers}`. Корневой `main.py` запускает Granian factory
`lib.app:create_app`; polling task создаётся и закрывается в lifespan.

Установите `thirdnews-contracts` из `packages/python/contracts` и используйте
асинхронный `IngestClient`. `NewsSubmission` требует `source + external_id` или
`idempotency_key`; endpoint всегда `/api/v1/news`. Значение `source` должно
совпадать со `slug` источника, заранее заведённого админом: приём отвечает
`409` на незнакомый источник.

Повторный обход уже собранного источника обязан пропускать обработанные
записи до обращения к сети. Отправка даст `duplicate`, но вложения к этому
моменту уже будут загружены, а невостребованная загрузка занимает место в
квоте незавершённых загрузок ключа (20 штук) до привязки к новости. Приватные файлы сначала
передаются через `await client.upload(...)`, затем completed upload id уходит в
`AttachmentInput.upload_intent_id`.

Парсер ограничивает время ответа и объём скачивания. Настроенные внутренние
адреса допустимы только как явные сервисные адаптеры; произвольный URL из
submission не должен обходить проверки главного сервиса.
