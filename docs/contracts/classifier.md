# Контракт классификатора

Классификатор — это HTTP-сервер с двумя ручками. Больше от него ничего не
требуется: ни общей БД, ни общего кода, ни того же языка.

```
GET  /manifest   → кто ты и что умеешь
POST /classify   → вот новость и таксономия, верни метки
```

Регистрируется в админке (`/api/v1/admin/classifiers`) с базовым URL и общим
секретом. Главный сервис сам зовёт его для каждой новости.

## `GET /manifest`

```json
{
  "slug": "my-classifier",
  "name": "Мой классификатор",
  "version": "0.1.0",
  "contract_version": "1.0",
  "facets": ["*"],
  "supports_async": false,
  "description": "..."
}
```

`facets` — оси, которые сервис умеет размечать, или `["*"]` для «любые, что
пришлют». Кнопка «Проверить связь» в админке дёргает именно эту ручку.

## `POST /classify`

Запрос:

```jsonc
{
  "request_id": "uuid задачи — верните его же в ответе",
  "news": {
    "id": "uuid",
    "title": "…",
    "body_md": "…",
    "source_link": "…",
    "source_text": "…",
    "published_at": "2026-09-01T10:30:00Z",
    "received_at":  "2026-09-01T10:31:02Z",
    "lang": "ru",
    "attachments": [{ "kind": "image", "url": "…", "mime": "image/jpeg" }],
    "extra": {}
  },

  // Актуальная таксономия. Она приходит в КАЖДОМ запросе — не кэшируйте её
  // надолго и не хардкодьте slug'и: админ добавляет оси на ходу.
  "taxonomy": {
    "facets": [
      {
        "slug": "importance",
        "title": "Важность",
        "description": null,
        "ai_hint": "Насколько новость важна для среднего студента.",
        "type": "single",          // single | multi
        "required": false,
        "values": [
          {
            "slug": "critical",
            "title": "Очень важно",
            "ai_hint": "дедлайны, отчисления, обязательные действия",
            "synonyms": ["дедлайн", "срочно"],
            "match_patterns": ["\\bдо \\d{1,2} \\w+\\b"]
          }
        ]
      }
    ]
  },

  "options": {
    "facets": [],            // если не пусто — отвечайте только по этим осям
    "min_confidence": 0.6,   // ниже этого ответ всё равно отбросят
    "config": {},            // произвольные настройки из админки (модель, промпт…)
    "callback_url": "https://news.example.edu/api/v1/classification/callback"
  }
}
```

Ответ:

```json
{
  "request_id": "тот же uuid",
  "classifier": "my-classifier",
  "labels": [
    { "facet": "importance", "value": "critical", "confidence": 0.9,
      "reason": "упомянут дедлайн" }
  ],
  "skipped": ["stream"],
  "meta": {}
}
```

Правила:

* `facet` и `value` — только slug'и из присланной таксономии. Выдуманные метки
  главный сервис молча отбрасывает.
* Для оси `single` вернуть больше одного значения — можно, но применится одно.
* `confidence` — честная уверенность от 0 до 1. От неё зависит, применится метка
  или останется предложением: см. `min_confidence` и `auto_apply` в реестре.
* `reason` попадает в админку и очень помогает при разборе спорных случаев.
* Ось, про которую вы не уверены, лучше не включать вовсе.

## Подпись запросов

Если у регистрации задан секрет, каждый запрос подписывается:

```
X-3rdnews-Timestamp: 1772534400
X-3rdnews-Signature: sha256=<hex>
```

где `hex = HMAC_SHA256(secret, f"{timestamp}.{raw_body}")`. Проверяйте подпись и
свежесть метки времени (окно — 5 минут). В Python это одна строка:

```python
from thirdnews_contracts import verify_signature
verify_signature(SECRET, raw_body, signature_header, timestamp_header)
```

## Медленные классификаторы

Если ответ не укладывается в таймаут (LLM, своя очередь), верните `202 Accepted`
с пустым телом, а результат позже отправьте на `options.callback_url`:

```
POST /api/v1/classification/callback
X-3rdnews-Timestamp / X-3rdnews-Signature — та же подпись, тот же секрет

{ "request_id": "…", "classifier": "my-classifier",
  "labels": [...], "error": null, "meta": {} }
```

Поле `error` вместо меток означает «не смог» — задача закроется, и новость не
будет ждать вас вечно. Укажите `"supports_async": true` в манифесте.

## Скелет на Python

```python
from thirdnews_contracts import ClassifyRequest, ProposedLabel
from thirdnews_contracts.worker import build_classifier_app

def classify(request: ClassifyRequest) -> list[ProposedLabel]:
    labels = []
    for facet in request.taxonomy.facets:
        ...
    return labels

app = build_classifier_app(
    slug="my-classifier", name="Мой классификатор",
    classify=classify, secret=os.getenv("CLASSIFIER_SECRET"),
)
```

`build_classifier_app` сам поднимает `/health`, `/manifest`, `/classify` и
проверяет подпись. Пользоваться им необязательно — это просто удобная обёртка.

Рабочие примеры: [`services/classifier-regex`](../../services/classifier-regex/app/main.py)
(без состояния, правила из админки) и
[`services/classifier-ai`](../../services/classifier-ai/app/main.py) (LLM через
OpenRouter, промпт собирается из таксономии).

См. также [руководство](../guides/writing-a-classifier.md).
