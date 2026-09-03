# Как написать классификатор

Классификатор получает новость вместе с актуальной таксономией и возвращает
метки. Полное описание протокола —
[`docs/contracts/classifier.md`](../contracts/classifier.md); здесь — как это
делается на практике.

## Главное правило

**Не хардкодьте оси и значения.** Админ добавляет ось «Факультет» или значение
«поток 2027» в интерфейсе, без деплоя. Ваш сервис должен идти по
`request.taxonomy.facets` и отвечать по тем осям, которые понимает, а остальные
пропускать.

Если сервис умеет только конкретные оси — перечислите их в манифесте (`facets`)
и/или укажите при регистрации: тогда лишнее ему просто не пришлют.

## Минимальный сервис

```python
import os
from thirdnews_contracts import ClassifyRequest, ProposedLabel
from thirdnews_contracts.worker import build_classifier_app


def classify(request: ClassifyRequest) -> list[ProposedLabel]:
    text = f"{request.news.title or ''}\n{request.news.body_md}".lower()
    labels: list[ProposedLabel] = []

    for facet in request.taxonomy.facets:
        if facet.slug != "importance":
            continue
        for value in facet.values:
            if value.slug == "critical" and "дедлайн" in text:
                labels.append(
                    ProposedLabel(
                        facet=facet.slug,
                        value=value.slug,
                        confidence=0.8,
                        reason="в тексте есть слово «дедлайн»",
                    )
                )
    return labels


app = build_classifier_app(
    slug="deadline-detector",
    name="Детектор дедлайнов",
    classify=classify,
    secret=os.getenv("CLASSIFIER_SECRET"),
    facets=["importance"],
)
```

Запускается как обычное FastAPI-приложение:
`uvicorn app.main:app --host 0.0.0.0 --port 8000`.

## Регистрация

Админка → **Классификаторы** → указать URL и секрет, либо через API:

```bash
curl -X POST "$NEWS_URL/api/v1/admin/classifiers" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Детектор дедлайнов","base_url":"http://my-host:8000",
       "secret":"...","priority":150,"min_confidence":0.6,"auto_apply":true}'
```

Что означают поля:

| Поле | Смысл |
| --- | --- |
| `priority` | кто побеждает при разногласии по одной оси; больше — сильнее |
| `min_confidence` | метки слабее порога сохраняются как предложение, но не применяются |
| `auto_apply` | `false` — сервис работает «в тени»: предложения видны редактору, но не влияют на выдачу |
| `facets` | пусто = спрашивать про все оси; иначе только про перечисленные |
| `config` | произвольный JSON, приходит в `options.config` — модель, промпт, пороги |
| `timeout_s` | сколько ждать ответа |

Хороший способ выкатить новый классификатор: `auto_apply: false`, посмотреть
неделю в админке на его предложения, потом включить.

## Медленные ответы

Если укладываться в таймаут не получается, верните `202` и позже отправьте
результат на `options.callback_url` — подписав тем же секретом. Так работает
LLM-классификатор при больших очередях.

## Что нельзя забывать

* **`request_id` из запроса возвращается как есть** — по нему находится задача.
* **`confidence` должна быть честной.** Она напрямую решает, применится метка
  или нет. Классификатор, который всегда пишет 1.0, ломает всю схему
  разрешения.
* **Ответ валидируется.** Метки с неизвестными slug'ами отбрасываются молча —
  если разметка «не появляется», проверьте, что вы берёте slug'и из
  присланной таксономии, а не из своих констант.
* **Проверяйте подпись**, если секрет задан. Иначе ваш сервис классифицирует
  всё, что ему пришлют.
* **Не пишите ничего в БД главного сервиса.** Единственный канал — ответ.

## Примеры в репозитории

* [`services/classifier-regex`](../../services/classifier-regex/app/main.py) —
  правила целиком берутся из `synonyms` / `match_patterns` присланной
  таксономии, то есть настраиваются в админке.
* [`services/classifier-ai`](../../services/classifier-ai/app/main.py) —
  промпт собирается из `title` / `description` / `ai_hint` осей и значений,
  модель и инструкции приходят в `config`; ответ модели фильтруется по
  таксономии, чтобы выдуманные метки не попали в базу.
