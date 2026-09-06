# Итог ревью

Найдено 1 Critical, 9 High и 7 Medium defects/gaps. Файлы не изменялись, коммиты не выполнялись, другие агенты не использовались. Тесты не запускались: pytest/uv и интеграционный стенд могут создавать кэши, контейнеры и данные, что противоречило бы строгому read-only.

Во время первой инвентаризации репозиторий менялся: `routes.py` был заменён монолитом из отдельных handler-модулей. После этого критические файлы были дважды проверены по SHA-256 и оставались стабильны. Findings относятся к финальному доступному снимку.

## Findings

### 1. [Critical] Ограничение в пять попыток превращает временный сбой NATS/БД в постоянную потерю событий

Почему проблема: outbox выбирает только строки с `attempts < max_attempts`; после последней ошибки событие остаётся `delivered_at=NULL`, но больше никогда не выбирается. JetStream consumer также получает `max_deliver=5` и делает немедленный `nak()` при ошибке handler. Краткий outage БД может за несколько доставок навсегда остановить обработку уже опубликованного события. DLQ/replay-пути нет.

Потерянный `search.projection.requested` оставляет PostgreSQL revision впереди search projection, после чего весь feed отвечает 503, а не только затронутая новость.

Reproducer/code evidence:

- Остановить БД во время NATS delivery или вызвать пять ошибок publish; восстановить сервисы. Строка outbox/сообщение остаётся, но больше не доставляется.
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/nats/outbox.py:65](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/nats/outbox.py:65)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/nats/consumer.py:52](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/nats/consumer.py:52)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/core/workers.py:165](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/core/workers.py:165)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/delivery.py:136](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/delivery.py:136)

Solution: outbox должен ретраиться бессрочно либо атомарно переходить в явный DLQ со штатным replay. Для JetStream нужны backoff/DLQ consumer, алерт и восстановление search projection напрямую из PostgreSQL. Добавить тест outage дольше retry budget.

### 2. [High] Две несовместимые реализации пересчёта labels нарушают shadow, priority и single cardinality

Почему проблема: pipeline сохраняет classifier `origin_key` как `slug:attempt_id`, но `EffectiveLabels` соединяет его с `Classifier.slug` по точному равенству. Priority становится нулевым. Shadow хранится с `origin="shadow"`, тогда как фильтр исключает только `origin="classifier" AND classifier.shadow`. Поэтому shadow может стать effective. Кроме того, эта реализация записывает все мнения с лучшим score, даже для single facet.

Manual label/release запускает именно ошибочную реализацию и может испортить другие, не изменявшиеся оси.

Reproducer/code evidence: получить два classifier-мнения по single facet или единственное shadow-мнение, затем вручную изменить другую ось. После recompute появятся два effective-значения либо shadow станет effective.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/labels.py:92](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/labels.py:92)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:601](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:601)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_news.py:254](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_news.py:254)

Solution: оставить один доменный алгоритм recompute. Связывать мнение с `classifier_id`, отдельно хранить attempt/provenance, явно исключать shadow и применять cardinality facet.

### 3. [High] Reprocess не может отозвать старое мнение classifier

Почему проблема: reprocess не создаёт новую `NewsVersion`. Новое мнение получает новый `origin_key`, а recompute читает все labels текущей версии без выбора последней успешной попытки. Для multi facet результаты накапливаются union-ом; для single побеждает наиболее уверенный исторический ответ. Пустой новый ответ не может удалить старое effective-значение.

Reproducer: classifier сначала возвращает `["A"]`, затем после reprocess — `[]` или `["B"]`. `A` останется effective либо сможет победить по confidence.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/news_admin.py:94](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/news_admin.py:94)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:620](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:620)

Solution: сохранять append-only историю, но materialized winner строить только из последнего успешного opinion-set каждого classifier/version. Пустой набор тоже должен быть явным мнением.

### 4. [High] Ошибка AI provider считается успешной классификацией и может привести к автопубликации

Почему проблема: classifier-ai ловит любую ошибку provider и возвращает HTTP 200, пустые labels и `trace.error`. Главный pipeline не рассматривает `trace.error`/`skipped` как failure, помечает attempt/job `succeeded`. Coordinator считает classifier успешным и допускает auto-publish.

Reproducer: provider возвращает 429/500, taxonomy не имеет required facets либо они заполнены source defaults. Новость публикуется без успешного AI ответа и без retry.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/classifier-ai/lib/interactor/classifier.py:199](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/classifier-ai/lib/interactor/classifier.py:199)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:377](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:377)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/coordinator.py:187](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/coordinator.py:187)

Solution: provider transport/protocol failure должен давать retryable classifier failure. Если error передаётся в контракте, main обязан отклонять такой response и не считать child успешным.

### 5. [High] Ошибки загрузки attachments теряются, после чего публикуется новость с битым media URL

Почему проблема: coordinator ждёт завершения attachment children, но не проверяет их успешность. При переходе к classifiers список attachment children заменяется новым списком. `_finish` видит только classifier jobs. При успешных classifiers новость можно auto-publish, хотя attachment `dead_letter/failed`. Public DTO при этом включает любой active attachment и генерирует media URL даже без `object_key`.

Reproducer: ingest с attachment URL, который возвращает 404 или блокируется SSRF. Дождаться исчерпания attachment retries; classifiers успешны — новость публикуется, `/media/{id}` возвращает 404.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/coordinator.py:137](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/coordinator.py:137)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/coordinator.py:180](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/coordinator.py:180)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/common.py:77](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/common.py:77)

Solution: сохранять результаты всех стадий в parent payload/attempt, считать attachment failure причиной `needs_review`, а public DTO должен включать только действительно доступные вложения.

### 6. [High] `Source.skip_classification` полностью игнорируется

Почему проблема: настройка хранится в модели, редактируется через API и UI, но coordinator создаёт jobs для всех enabled classifiers без проверки источника. Новость отправляется AI вопреки явному запрету — это privacy/cost defect.

Reproducer: установить source `skip_classification=true`, ingest новость этого source; в БД появятся classification jobs, а body будет отправлен classifier.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/postgres/models/source.py:30](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/postgres/models/source.py:30)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/coordinator.py:156](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/coordinator.py:156)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/apps/web/src/pages/Sources.tsx:99](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/apps/web/src/pages/Sources.tsx:99)

Solution: вычислять политику классификации из связанных source rows до создания child jobs. Для merge с несколькими sources нужна явно определённая fail-closed семантика.

### 7. [High] TOCTOU при upload completion позволяет финализировать не те байты, чей SHA-256 проверен

Почему проблема: код сначала читает и хеширует временный объект, затем отдельной операцией копирует его. Оставшийся presigned PUT может заменить temp object между hash и copy. После копирования проверяется только размер, не digest. Атакующий может подменить объект содержимым того же размера.

Reproducer: начать `/uploads/complete`; после `inspect_and_hash`, но до `copy_object`, повторить presigned PUT с другими байтами той же длины и прежними metadata. Финальный объект получит заявленный digest в metadata, но фактические байты будут другими.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/s3/object_store.py:173](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/s3/object_store.py:173)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/s3/object_store.py:197](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/s3/object_store.py:197)

Solution: conditional copy по проверенному version/ETag либо повторная проверка SHA-256 финального объекта до commit. Предпочтительно versioned/object-lock staging и атомарная проверка неизменности source generation.

### 8. [High] Merge/split перемещают submissions, но оставляют attachments и manual provenance у старой новости

Почему проблема: операции меняют `NewsSourceLink.news_id` и `Submission.news_id`, но не `Attachment.news_id`, `NewsLabel`, `manual_facets` и связанные provenance decisions. После merge target не получает вложения source; после split новая новость не получает attachments выбранных submissions. Manual labels не переносятся и не оформляются как reviewable provenance.

Reproducer: создать news с двумя submissions, по одному attachment на каждый, затем split одного submission. Вложение останется у исходной news. Аналогично merge оставит вложения на archived source.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/news_admin.py:111](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/news_admin.py:111)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/news_admin.py:143](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/news_admin.py:143)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/postgres/models/attachment.py:23](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/postgres/models/attachment.py:23)

Solution: транзакционно перераспределять attachment ownership по submission, сохранять manual opinions как provenance rows и переводить обе стороны в review до явного подтверждения.

### 9. [High] Scores остаются устаревшими после manual labels и изменения editorial rules

Почему проблема: scoring вызывается только pipeline-реализацией recompute. `EffectiveLabels`, используемый manual endpoint, меняет effective labels, но не пересчитывает urgency/impact/editorial_priority. Создание или ревизия editorial rule также не перерасчитывает существующие новости. В результате facets и scores описывают разные состояния, а Meili индексирует старые числа.

Reproducer: правило даёт urgency=100 для label A; вручную очистить facet A. Effective label исчезнет, urgency останется 100. Или добавить новое правило — существующие строки не изменятся.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/labels.py:92](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/labels.py:92)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:680](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:680)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_catalog.py:306](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_catalog.py:306)

Solution: единый materialization transaction должен одновременно пересчитывать effective labels и scores. Rule revision должна ставить versioned bulk recalculation jobs.

### 10. [High] Classifier probe сам добавляет атакуемый host в SSRF allowlist

Почему проблема: endpoint берётся из БД, затем его hostname автоматически передаётся в `with_service_hosts`. Для такого host `SafeFetcher` разрешает private/link-local addresses. Это полностью обходит защиту `is_global`.

Reproducer: admin регистрирует `http://169.254.169.254/latest` либо `http://127.0.0.1:...`, затем вызывает probe. Host становится trusted и запрос выполняется из API network namespace.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_catalog.py:248](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_catalog.py:248)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/http/safe_fetcher.py:272](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/http/safe_fetcher.py:272)

Solution: probe должен применять фиксированный operator-controlled allowlist. Никогда не доверять host только потому, что он записан в classifier endpoint.

### 11. [Medium] Заголовок `Idempotency-Key` фактически невозможно использовать самостоятельно

Почему проблема: route принимает заголовок, а interactor умеет его объединять с payload, но `NewsSubmission` валидируется FastAPI до вызова handler и требует idempotency key внутри body. Запрос с корректным header и без body key получит 422.

Дополнительно hash считается из body: перенос одинакового ключа из header в payload изменит digest и даст ложный 409.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/packages/python/contracts/thirdnews_contracts/ingest.py:58](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/packages/python/contracts/thirdnews_contracts/ingest.py:58)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/ingest.py:45](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/ingest.py:45)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/ingest.py:51](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/ingest.py:51)

Solution: валидировать combined identity после объединения transport header/body и нормализовать key перед вычислением payload hash.

### 12. [Medium] Разрешённые taxonomy rename/kind-change оставляют сломанные ссылки и невалидную materialization

Почему проблема: API разрешает менять facet slug и `multi→single`. Handler обновляет только `news.manual_facets` и search revision. Он не пересчитывает effective labels и не обновляет JSON-ссылки в editorial rules, source defaults, classifier allowed_axes и API-key presets.

Reproducer: facet с двумя effective values изменить с multi на single — оба останутся effective. Переименовать slug — source defaults начнут падать как unknown facet, classifier allowlist перестанет совпадать, read preset может отвечать 400.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_taxonomy.py:92](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_taxonomy.py:92)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/dto/requests/facet_input.py:4](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/dto/requests/facet_input.py:4)

Solution: либо сделать slug/kind неизменяемыми, либо реализовать versioned migration workflow со ссылочным анализом, массовым recompute и обязательным review.

### 13. [Medium] Три фильтра очереди Review UI молча не работают

Почему проблема: UI посылает `gold`, `source`, `unlabelled_facet`, но admin endpoint принимает только `status`, `q`, `limit`, `offset`. FastAPI игнорирует неизвестные query params, поэтому пользователь видит нефильтрованные результаты без ошибки.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/apps/web/src/pages/Review.tsx:64](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/apps/web/src/pages/Review.tsx:64)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_news.py:65](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/admin_news.py:65)

Solution: реализовать server-side параметры и их индексы либо убрать элементы UI. Добавить browser/API contract tests.

### 14. [Medium] `PATCH body_md=null` приводит к 500 вместо валидационной ошибки

Почему проблема: DTO разрешает `body_md: null`, interactor переносит null в новую immutable version, но DB column `body_md` — NOT NULL. `IntegrityError` handler не ловит.

Reproducer: editor выполняет `PATCH /api/v1/admin/news/{id}` с `{"body_md":null}`; результат — internal server error.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/dto/requests/news_edit.py:7](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/dto/requests/news_edit.py:7)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/news_admin.py:45](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/news_admin.py:45)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/postgres/models/news_version.py:36](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/infra/postgres/models/news_version.py:36)

Solution: запретить null для non-nullable fields; для nullable clear semantics определить явно. Domain validation должна происходить до flush.

### 15. [Medium] RSS применяет ACL после глобального LIMIT 100

Почему проблема: сначала выбираются 100 самых новых опубликованных новостей без principal preset, затем запрещённые элементы удаляются в Python. Пользователь может получить пустой RSS, хотя более старые разрешённые новости существуют. Это не та же ACL-пагинация, что feed.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/delivery.py:276](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/handlers/delivery.py:276)

Solution: выразить preset в SQL до `ORDER BY/LIMIT`, используя тот же policy builder, что для detail/feed/media.

### 16. [Medium] 30-дневный raw-AI retention не гарантирован, часть provider error хранится открыто

Почему проблема: purge использует `completed_at`; незавершённые/stuck attempts не очищаются вообще, а долго выполнявшаяся попытка хранит payload до 30 дней после completion, а не после записи. Provider error message сохраняется в plaintext `error_detail`, хотя он может содержать отражённый фрагмент prompt/news.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:108](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:108)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/classifier-ai/lib/interactor/classifier.py:123](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/classifier-ai/lib/interactor/classifier.py:123)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:377](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/main/lib/interactor/processing/pipeline.py:377)

Solution: хранить `raw_stored_at/raw_expires_at`, очищать независимо от attempt status; plaintext error ограничивать opaque code. Дешифрование должно идти через отдельный audited endpoint — сейчас `raw_audit` scope фактически не используется.

### 17. [Medium] Parser TiMe fail-open при пустом admin token

Почему проблема: middleware проверяет bearer token только если `PARSER_API_TOKEN` непуст. Compose по умолчанию передаёт пустое значение и публикует сервис на localhost. Любой локальный процесс может читать private channel metadata, менять selected channels и запускать poll.

- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/parser-time/lib/app.py:504](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/parser-time/lib/app.py:504)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/parser-time/lib/core/config.py:35](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/services/parser-time/lib/core/config.py:35)
- [/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/docker-compose.yml:225](/Users/space/Documents/program_proj/Projects/cu-3rd-party/proj10-news/3rd-news/docker-compose.yml:225)

Solution: отказываться стартовать management API без token либо отключать все non-health routes. Использовать constant-time comparison и не публиковать порт без явного профиля управления.

## Краткая архитектура

Главный сервис — FastAPI/Granian с раздельными process roles: API, outbox publisher, pipeline worker и search indexer. PostgreSQL хранит submissions, immutable news versions, opinions/effective labels, jobs/attempts, outbox/inbox и search checkpoints.

Pipeline организован как parent job: remote attachments → classifier jobs → labels/scoring → search projection. AI и regex classifier — отдельные подписанные Ed25519 HTTP-сервисы. NATS JetStream используется как durable delivery/wakeup слой, Meilisearch — производная read model. Garage хранит uploads; public media проходит через ACL-aware API proxy. UI — React/Bun за Caddy.

Положительные стороны: AI-вызов вынесен из DB transaction; callback имеет generation/version fencing и server-side axis normalization; remote attachment fetcher пинит DNS answers; public body рендерится React-ом как текст, RSS экранируется; media выдаётся с authorization и attachment disposition; score ranges закреплены DB constraints; `httpx` в исполняемом коде не найден.

## Тесты и качество

В Python-коде найдено 173 test functions, из них 53 в `services/main`. Есть хорошие точечные проверки:

- source/parser/manual precedence и manual empty;
- concurrent job/outbox/inbox claiming;
- stale classifier attempt fencing;
- Ed25519/body binding;
- SSRF для обычного remote fetch;
- search reindex barrier;
- session/JWT revocation;
- score boundaries и NATS sensitive-field rejection.

Основные gaps:

- `make test` явно исключает integration/e2e;
- integration suite требует внешний `TEST_DATABASE_URL` и иначе пропускается;
- нет реального E2E NATS–PostgreSQL–Meili–Garage;
- нет тестов exhaustion retry budget/DLQ;
- нет upload overwrite race test;
- нет merge/split attachment/provenance tests;
- нет multi-classifier/manual/shadow recompute tests;
- provider failure test закрепляет ошибочное «error as successful response» поведение;
- нет тестов `skip_classification`, rule recalculation, header-only idempotency;
- для `apps/web/src` нет собственных frontend tests, а общий quality runner UI не проверяет.