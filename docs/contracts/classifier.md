# Classifier protocol v2

Узел предоставляет `GET /manifest`, `GET /health/healthz`,
`GET /health/startup`, `GET /health/ready` и `POST /classify`.

`ClassifyRequest` связывает `request_id`, `job_id`, `attempt_id`, id и версию
новости, версию taxonomy и `options.allowed_axes`. Узел возвращает только
значения из присланной taxonomy и только для разрешённых осей. Gold-пример не
может попасть в `examples`: модель `LabeledExample` допускает лишь
`is_gold=false`.

`examples` по умолчанию выключены. При явном включении главный сервис выбирает
ограниченное число опубликованных non-gold новостей с актуальным ручным
решением, включая значимую пустую разметку. Текущая новость и любые новости,
связанные с источником `skip_classification=true`, исключаются запросом к БД.
Классификатор получает только разрешённые ему и включённые оси/значения.

Синхронный узел отвечает 200 `ClassifyResponse`. Узел с
`supports_async=true` может ответить 202, после чего отправляет тот же результат
на подписанный `options.callback.url` не позже `deadline_at`. Callback после
deadline игнорируется. `job_id`, `attempt_id`, `news_id` и `news_version`
защищают актуальную попытку от позднего результата.

`ClassifyResponse.status` имеет ровно два состояния. `completed` не содержит
`error` и может содержать labels. `failed` обязательно содержит структурированный
`error` (`code`, безопасное `message`, `retryable`) и никогда не содержит labels.
Транспортная или протокольная ошибка provider возвращается как `failed`, даже
если синхронный HTTP-ответ узла имеет статус 200. Получатель обязан считать такой
результат неуспешной попыткой, применить retry policy и не применять opinions.

`ProposedLabel` содержит `axis`, `value`, confidence 0–1, reason и evidence.
AI-узел также возвращает `AITrace`: provider/model/parameters, версии prompt,
schema и taxonomy, исходный provider request, сырой response, длительность и
диагностическую ошибку. Поле `trace.error` предназначено только для аудита;
машинный исход определяется `status` и `error`. Главный сервис шифрует raw
payload и удаляет его через 30 дней.

Каждый запрос подписан compact JWT в `Authorization: Bearer`. Разрешён только
`alg=Ed25519`. Claims: `iss`, `aud`, `iat`, `exp`, `jti`, `job_id`,
`attempt_id`, `node_id`, `body_sha256`. Максимальная жизнь 300 секунд.
Получатель проверяет issuer, audience, срок, exact body digest, назначенный
node и одноразовость jti. Callback подписывается отдельным private key узла;
main проверяет зарегистрированный public key.
