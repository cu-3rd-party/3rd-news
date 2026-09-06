# Аналитический отчёт о переписывании 3rd-news

Дата: 2026-09-06. Рабочее дерево без коммитов. Отчёт обновляется по итогам
последней проверки; непроверенные этапы не считаются завершёнными.

## Реализация и архитектура

Все пять Python-сервисов следуют примеру backend: `services/<name>/lib`,
`test`, `main.py`, `Dockerfile`, `pyproject.toml`, `uv.lock` и локальная `.venv`.
Каталоги `src/thirdnews`, `bootstrap`, `presentation`, прежние `app`, корневые
legacy-тесты и `requirements.txt` заменённых сервисов удалены. Предоставленный
пользователем каталог `backend` сохранён как пример. Общий Python-код находится
только в `packages/python/contracts`; каждый сервис устанавливается и проверяется
в собственной среде Python 3.14.7. Запрещённые HTTP-клиенты не используются.

В главном сервисе `lib/domain` содержит независимые сущности/инварианты,
`lib/dto` — входные модели, `lib/interactor` — прикладные сценарии,
`lib/infra` — PostgreSQL, auth, NATS, Meilisearch, S3 и HTTP-адаптеры,
`lib/handlers` — HTTP-маршруты, `lib/core` — настройки/инициализацию/workers.
ORM-модели разделены по файлам и не заменяют доменные сущности.
Один образ запускает API и три роли workers. Ресурсы создаются/закрываются
через lifespan и `AppResources`; миграции выполняются отдельным процессом.

PostgreSQL является источником истины: submissions, версии новостей, происхождение,
мнения, effective labels, правила, задания/попытки, outbox/inbox, upload intents,
аудит и checkpoints поиска. Доставка допускает повторы, но применение защищено
inbox, ownership и version fences. Транспортные отказы outbox повторяются без исчерпания с ограниченным backoff;
невалидные локальные события помещаются в карантин с admin replay. Исчерпанные
прикладные доставки consumers сохраняются в подтверждаемой DLQ; изменение видимости блокирует устаревшую поисковую выдачу.

Внешние AI/regex-классификаторы и RSS/TiMe-парсеры знают только общий контракт.
AI по умолчанию работает через OpenAI-совместимый протокол с aiohttp. CPU-стенд
Ollama использует явно настроенный native transport с `think=false`, поскольку
OpenAI `/v1` в проверенной версии Ollama не применил отключение reasoning к Qwen3;
обоим transport передаётся одна strict JSON Schema. Таксономия и редакционные
правила остаются данными; ручное пустое решение сохраняет приоритет. UI перенесён
в `apps/web` без редизайна. Подписки, уведомления, OCR и транскрибация не входят
в согласованный этап.

Подробности: [архитектура](architecture.md), [авторизация](auth.md),
[HTTP OpenAPI](../contracts/http/openapi.json), [ingest](contracts/ingest.md),
[classifier](contracts/classifier.md), [delivery/recovery](contracts/delivery.md).
Wire `CONTRACT_VERSION=2.0`; Python-дистрибутив contracts имеет версию 2.0.2.
Это несовместимый чистый запуск, без переноса прежней БД/API. Старые данные,
пользовательские `.env` и прежние Docker volumes не удалены.

## Проверки и практические границы

Зафиксированы зелёные Ruff format/check, ty и basedpyright во всех семи
Python-проектах; общие команды представлены в make/just. Alembic upgrade/check
и SQL каждой миграции через Squawk прошли. Squawk разрешает осознанный выбор
VARCHAR/INTEGER, а в миграции расширения строк отдельно документирован безопасный
переход к большей длине; проверки блокировок/таймаутов не отключены.

[Отчёт QA](qa-report.md) содержит точные команды: итоговые 258 Python unit-тестов,
50 PostgreSQL integration-тестов и 3 frontend-теста прошли. Полный E2E последнего
образа завершился за 16,91 секунды.
Прогон с измерением покрытия основного сервиса дал 98 passed и 55% совокупного
покрытия строк/ветвей (до последних добавленных тестов). Это не 100% покрытия.
Mutation-проверка небольшого доменного ядра: 20/20 мутантов убиты; результат не
распространяется на весь pipeline. Две дополнительные Hypothesis-проверки выполняют
по 250 сгенерированных случаев: враждебная разметка не расширяет разрешённые оси
и cardinality, диапазоны importance остаются корректными.

Настоящие PostgreSQL/NATS/Meilisearch/Garage использованы для конкуренции,
rollback, повторной доставки, подтверждения поисковых задач, потоковой
переиндексации и закрытых объектов. Live NATS проверил отказ DLQ: доставки
`[1,2,3,4]`, один сохранённый failure record, `ack_pending=0`; после исправления
shutdown завершился примерно за четыре секунды без DrainTimeoutError.

[Замеры](verification/README.md): по 20 synthetic submissions, concurrency 10,
с одной и четырьмя pipeline-репликами. Все 40 опубликованы. Один worker:
pipeline p95 11196 ms, 1.786 items/s; четыре: p95 11260 ms, 1.775 items/s.
Выборка мала и исключает AI. Она подтверждает работоспособность нескольких
workers, но не линейное масштабирование, production capacity или SLO.
Моментальный расход памяти workers — около 86–96 MiB; это не измерение пика.
Отозванный ключ и анонимный ingest дали 401, отсутствие CSRF — 403.

Gitleaks 8.30.1 проверил итоговый снимок из 376 файлов кандидата без находок; отдельный
искусственный токен дал одну ожидаемую находку, подтверждая работоспособность
сканера. Локальные ignored secrets и история Git в этот проход не входили.

Все семь Python dependency audits и Bun audit прошли без известных уязвимостей
установленных прикладных зависимостей. Это не означает отсутствие уязвимостей
в базовых образах: [отдельный security-отчёт](image-security-report.md) сохраняет
полные no-fix findings Debian и оценку достижимости. Caddy собран с обновлёнными Go и зависимостями: конечный web-образ
имеет 0 Critical/High и 0 fixable; остаются три Medium alias одного BusyBox CVE. GitHub Actions настроен, но удалённый CI не запускался.

Браузерная ручная проверка UI не подтверждена: инструмент открытия локального
стенда вернул `net::ERR_BLOCKED_BY_CLIENT`. Production TLS/ACME, резервное
копирование, длительные soak-тесты и качество AI на размеченном корпусе не
подтверждены. Маленькая CPU-модель предназначена только для smoke-проверки.

## Реестр первоначального независимого ревью

Первичное ревью выполнял отдельный sol high с чистым контекстом, только описанием
системы/инвариантов и read-only доступом. Его неизменённый результат сохранён
в [review-independent.md](review-independent.md). Ниже фиксируются исправления,
а не переписывается первоначальное заключение.

| Находка | Почему проблема | Решение | Доказательство |
| --- | --- | --- | --- |
| [Critical] Исчерпание доставки | Outage навсегда исключал событие из обработки | Подтверждаемая DLQ, backoff, список outbox и аудитируемый replay | Live JetStream outage/redelivery + repository regression |
| [High] Два алгоритма labels | Разные priority/shadow/single правила | Единая materialization | PostgreSQL label regressions |
| [High] Старые мнения reprocess | Пустой новый ответ не отзывал старые метки | Выбор последней успешной попытки, включая пустую | Latest-attempt/empty-result regression |
| [High] Ошибка AI считалась успехом | Возможна автопубликация при provider failure | Обязательный status, retryable error, fail-closed pipeline | Contract/node tests; provider failure оставил needs_review; реальный `qwen3:0.6b` затем вернул completed и допустимую метку |
| [High] Ошибка вложения забывалась | Pipeline мог опубликовать сломанное вложение | Ошибка стадии требует review, DTO отдаёт только stored objects | Coordinator и attachment DTO tests |
| [High] Игнорировался skip_classification | Текст уходил AI вопреки настройке источника | Политика проверяется до child jobs; любой запрещающий source блокирует | Coordinator regression и queue load без classifier jobs |
| [High] TOCTOU upload complete | PUT мог подменить байты между hash и copy | Повторный SHA финального объекта до commit, удаление несоответствия | Детерминированная same-size race regression |
| [High] Merge/split теряли связи | Вложения и manual provenance оставались у другой news | Транзакционное перераспределение ownership и сохранение происхождения | PostgreSQL merge/split regression |
| [High] Устаревшие scores | Manual/rule change не менял importance | Совместный пересчёт labels/scores и новая search revision | Manual empty/rule revision integration |
| [High] SSRF probe | Endpoint сам становился доверенным host | Только фиксированный operator allowlist | Probe policy regression |
| [Medium] Header idempotency | Валидация раньше объединения header/body | Combined identity и canonical fingerprint | Header-only и повтор с переносом ключа |
| [Medium] Taxonomy rename/kind | JSON-ссылки и cardinality становились неверными | Slug/kind неизменяемы; отображаемые данные редактируемы | Taxonomy handler regression |
| [Medium] Фильтры Review | UI получал нефильтрованные данные | Реализованы gold/source/unlabelled_facet | PostgreSQL admin-filter tests |
| [Medium] body_md=null | PATCH приводил к 500 | Явная 422-валидация | Handler regression |
| [Medium] RSS ACL после LIMIT | Разрешённые старые новости исчезали | SQL ACL до ограничения количества | RSS ACL regression |
| [Medium] Raw AI retention/доступ | Stuck attempts не очищались, ошибки могли раскрывать payload | Started-at retention, encrypted failures, scope+audit endpoint | Retention/auth regression и аудитированная диагностика synthetic failure |
| [Medium] TiMe token fail-open | Пустая настройка открывала управление | Non-health 503 без токена, constant-time check | TiMe negative tests |

Дополнительно QA исправил concurrent-ingest IntegrityError, stale JWT roles,
неограниченный HTTP transport, нечисловой JSON outbox, Meili filter settings,
потоковую переиндексацию, classifier runtime, stale tool paths и PostgreSQL
deadlock при одновременном создании попыток. Зафиксированы отдельные регрессии.

## Финальная верификация

Второе независимое ревью с чистым контекстом сохранено без изменений в
[review-second-independent.md](review-second-independent.md). Реестр двадцати
находок и доказательств исправления — [review-second-resolution.md](review-second-resolution.md).
Разработчики также закрыли обнаруженные при перепроверке пограничные случаи:
ошибка транспорта ValueError не карантинит outbox, неизвестное имя environment
не обходит production validators, ручное пустое решение сохраняется при
выключении и повторном включении оси.

Полный Compose smoke прошёл с непустой таксономией и настоящим вызовом Qwen3:
идемпотентность и конфликт payload, batch isolation, immutable upload promotion,
публикация, подтверждённый поиск, закрытые GET/HEAD/Range/RSS и отзыв сессии.
[Машинный результат](verification/compose-smoke.json). Отдельный реальный
IngestClient получил временный API-ключ, отправил submission, загрузил и привязал
вложение; после отзыва ключа запрос был запрещён. Live NATS/Garage/Meilisearch
прошли — [вывод](verification/live-integration.txt).

Все обнаруженные прикладные дефекты из двух ревью исправлены и повторно проверены.
Это не означает полного production допуска: ручной браузерный UI-прогон,
production TLS/ACME, длительная нагрузка, качество AI и no-fix системные CVE
остаются ограничениями, описанными выше. Коммиты не создавались.
