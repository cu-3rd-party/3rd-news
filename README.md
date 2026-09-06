# 3rd-news

Университетский агрегатор новостей: принимает оригиналы, асинхронно получает
классификацию от внешних сервисов, нормализует результат и публикует закрытую
ленту, RSS и API. Версия 2 предназначена для **новой базы**. Старые базы и
Docker volumes автоматически не изменяются и не удаляются.

## Архитектура

- `services/main`: один Python-пакет `lib` и один образ, режимы `api`,
  `worker-outbox`, `worker-pipeline`, `worker-index`.
- `services/classifier-*`, `services/parser-*`: самостоятельные внешние программы.
  Главный сервис знает только их версионированный HTTP/JSON-контракт.
- `packages/python/contracts`: общие Python DTO, подписи и SDK. Общий Python-код
  размещается только внутри `packages/python`.
- `contracts`: машинные схемы; `docs/contracts`: описание контрактов.
- `apps/web`: существующие сценарии админки, перенесённые без редизайна на
  актуальные React 19, Vite 8 и TypeScript 7.
- `infra`: Compose, Caddy и инициализация инфраструктуры.

PostgreSQL — источник истины. Outbox записывается в одной транзакции с новостью,
NATS JetStream обеспечивает повторную доставку, обработчики проверяют inbox и
версии попыток. Meilisearch — восстанавливаемая поисковая проекция. Garage S3
хранит закрытые вложения. Сведения о конкретных источниках и классификаторах
задаются регистрациями, а не импортами внутри главного сервиса.

Таксономия динамическая. Мнения и версии сохраняются отдельно; ручные решения
не затираются AI. `importance = urgency + impact + editorial_priority`, каждый
компонент 0–100. Начальные правила нейтральны; примеры правил выключены.

## Запуск

Требуются Docker Engine и Docker Compose v2. Новая система использует отдельное
имя проекта `thirdnews-v2`, не старое `3rd-news`.

```sh
docker compose up -d --build
docker compose logs -f api worker-outbox worker-pipeline worker-index
```

Первый запуск создаёт случайные ключи и пароли в отдельных config volumes.
Секреты не встроены в образы и не печатаются в startup logs. Ollama автоматически
загружает `qwen3:0.6b`; первый запуск требует доступа к registry и загрузке модели.
Общий AI-классификатор по умолчанию использует OpenAI-совместимый протокол и strict
JSON Schema. CPU smoke-профиль задаёт `PROVIDER_PROTOCOL=ollama-native`, потому что
Ollama 0.33 с Qwen3 игнорирует отключение reasoning в OpenAI `/v1` и превышает
deadline. Адаптер вызывает `/api/chat` с `think=false` и той же JSON Schema; это
явное ограничение проверочного стенда, а не контракт production-провайдера.
CPU-профиль служит воспроизводимым стендом, а не обещанием production SLO.

Админка: http://localhost:8080. Начальный пользователь: `admin@example.edu`.
Получить сгенерированный пароль локально:

```sh
docker compose exec api thirdnews-bootstrap-password
```

```sh
docker compose up -d --scale worker-pipeline=4
docker compose run --rm migrate
docker compose down
```

Миграции выполняет отдельный процесс; API-реплики не запускают Alembic.
Команда остановки не удаляет volumes. Файловая выдача проходит проверку прав
на новость; порт 8081 принимает только подписанные PUT uploads.

Для TLS предусмотрен `infra/compose.production.yml`: задать `SITE_ADDRESS`,
`UPLOAD_ADDRESS`, `FILE_PUBLIC_SCHEME=https`, `FILE_PUBLIC_HOST=<upload-domain>`,
`FILE_PUBLIC_PORT=443`, настроить DNS и
запустить Compose с обоими файлами. Production overlay открывает только proxy
на 80/443; PostgreSQL, NATS, Meilisearch и Garage admin наружу не публикуются.

## Контракты

- `POST /api/v1/news` и `/news/batch` → `202`, идентификатор submission.
- Обязательны `source + external_id` либо стабильный ключ идемпотентности.
  Повтор с другим содержимым даёт конфликт; одинаковый текст не является ключом.
- `GET /api/v1/submissions/{id}` — состояние обработки.
- `POST /api/v1/uploads/presign`, `/uploads/complete` — безопасная загрузка.
- `GET /api/v1/feed`, `/news/{id}`, `/taxonomy`, `/rss.xml` — закрытая выдача.
- `/api/v1/admin/*` — редактура, таксономия, источники, ключи и классификаторы.
- `/health/live`, `/health/ready` — состояние процесса и ресурсов.

Лента, RSS и медиа требуют авторизации; API-ключи передаются заголовками,
не query string. После ограничения видимости устаревшая поисковая проекция
не выдаётся. Классификаторы получают подписанные задания с ограничением осей;
повторы и поздние callbacks не меняют завершённую или новую попытку.

Файлы с текстом обрабатываются; OCR и транскрибации нет. Невалидные AI-ответы
не публикуются автоматически. Сырые AI payloads защищены отдельным ключом и
удаляются через 30 дней; проверенные результаты и метаданные сохраняются.

## Разработка и проверки

Python 3.14, только uv; HTTP через aiohttp, без HTTPX. Каждый сервис имеет свои
`pyproject.toml`, `uv.lock`, `.venv`. Factory, lifespan, управление ресурсами,
request ID, ошибки и health endpoints следуют исходному примеру `backend`.

```sh
make sync
make test
make lint
make fmt
make integration
make mutation
make audit
make web
```

Те же цели доступны через `just`. Форматирование в `lint` проверяется без
изменений; `fmt` исправляет код. Frontend использует только bun.
Интеграционные тесты требуют отдельного тестового стенда; не указывайте им
рабочую базу. Результаты проверок и ограничения фиксируются в `docs/rewrite-report.md`.

Новые интерфейсы админки, OCR/транскрибация и доставка уведомлений в эту версию
не входят. Подписки добавляются позднее через событийные контракты.
