# thirdnews-contracts

Публичный контракт платформы 3rd-news: pydantic-модели, HMAC-подпись, клиент
для парсеров и хелпер для классификаторов.

Пакет ничего не знает про главный сервис и ни от чего в нём не зависит — его
можно поставить в совершенно посторонний репозиторий.

```bash
pip install "thirdnews-contracts @ git+https://github.com/<org>/3rd-news.git#subdirectory=packages/contracts"
# для классификатора нужен ещё FastAPI:
pip install "thirdnews-contracts[server] @ git+..."
```

## Что внутри

| Модуль | Для кого |
| --- | --- |
| `ingest` | `NewsSubmission`, `AttachmentInput`, `IngestResult` — что шлёт парсер |
| `client` | `IngestClient` — готовая отправка, включая multipart с файлами |
| `taxonomy` | `Taxonomy`, `FacetSchema`, `FacetValueSchema` — схема классификации |
| `classifier` | `ClassifyRequest`, `ClassifyResponse`, `ProposedLabel`, `ClassifierManifest` |
| `worker` | `build_classifier_app()` — превращает функцию в совместимый сервис |
| `signing` | `sign_payload` / `verify_signature` — подпись запросов между сервисами |
| `news` | `NewsItem`, `NewsPage` — то, что читает клиент из выдачи |

## Парсер за пять строк

```python
from thirdnews_contracts import IngestClient, NewsSubmission

client = IngestClient("https://news.example.edu", api_key="tnk_...")
client.submit(NewsSubmission(body_md="…", source_text="Деканат", external_id="1"))
```

## Классификатор за десять

```python
from thirdnews_contracts import ClassifyRequest, ProposedLabel
from thirdnews_contracts.worker import build_classifier_app

def classify(request: ClassifyRequest) -> list[ProposedLabel]:
    return []

app = build_classifier_app(slug="my", name="Мой", classify=classify, secret=SECRET)
```

Пользоваться пакетом необязательно: контракт — это HTTP + JSON, см.
`docs/contracts/` в корне репозитория.
