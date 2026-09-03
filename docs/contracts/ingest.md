# Контракт приёма новостей

Это всё, что нужно знать, чтобы написать парсер. Реализация парсера может быть
на любом языке — здесь описан чистый HTTP.

## Ручка

```
POST /api/v1/ingest/news
X-API-Key: tnk_...
Content-Type: application/json
```

Ключ выпускается в админке с правом `ingest`. Если ключ привязан к источнику,
`source_key` можно не передавать.

## Тело запроса

```jsonc
{
  // Стабильный идентификатор поста внутри источника: id сообщения, guid, ссылка.
  // Вместе с source_key делает приём идемпотентным.
  "external_id": "12345",

  // Slug источника в админке. Если такого нет — он создастся автоматически.
  "source_key": "tg-dekanat-fkn",

  "title": "Заголовок (необязательно)",

  // Текст в Markdown. Длина не ограничивается сервисом.
  "body_md": "Полный текст новости в **markdown**...",

  // Ссылка на оригинал...
  "source_link": "https://t.me/dekanat_fkn/12345",
  // ...или, если ссылки нет, человекочитаемое название канала.
  "source_text": "Деканат ФКН, Telegram",

  // Время публикации в источнике. Время прихода в сервис проставляется сам.
  "published_at": "2026-09-01T10:30:00+03:00",

  "lang": "ru",

  "attachments": [
    { "kind": "image", "url": "https://.../poster.jpg", "caption": "Афиша" },
    { "kind": "pdf",   "url": "https://.../schedule.pdf", "filename": "schedule.pdf" }
  ],

  // Метки, в которых парсер уверен. Всё остальное решают классификаторы и
  // редакторы. Формат: {"slug-оси": ["slug-значения", ...]}
  "labels": { "stream": ["2025"] },

  // Произвольные данные парсера, сервис их не трогает.
  "extra": { "views": 1200 }
}
```

Обязательно только `body_md` плюс хотя бы одно из `source_link`, `source_text`,
`source_key`. `kind` вложения — `image` | `pdf` | `video` | `audio` | `file`.

## Ответ

```json
{ "id": "9a1f...", "status": "created", "received_at": "2026-09-01T07:31:02Z" }
```

`status` — `created` или `duplicate`. **Дубликат не ошибка**: перечитывайте
ленту с начала сколько угодно, состояние хранить не нужно.

## Загрузка файлов напрямую

Если файл нельзя отдать ссылкой (например, он лежит только в Telegram),
отправьте `multipart/form-data`: поле `payload` — тот же JSON, остальные поля —
файлы, а во вложении вместо `url` укажите `upload_name` с именем поля.

```
POST /api/v1/ingest/news
Content-Type: multipart/form-data

payload = {"body_md":"...","source_text":"...",
           "attachments":[{"kind":"image","upload_name":"cover"}]}
cover   = <бинарные данные>
```

Ограничение размера — `NEWS_MAX_ATTACHMENT_BYTES` (по умолчанию 512 МиБ).
Вложения по URL скачиваются воркером асинхронно, поэтому в первые секунды
`attachment.status` будет `pending`.

## Пакетная отправка

```
POST /api/v1/ingest/news/batch
{ "items": [ {...}, {...} ] }   →   { "results": [ {...}, {...} ] }
```

До 200 новостей за раз, только вложения по URL. Дубликаты отмечаются
по-элементно и не роняют пакет.

## Ошибки

| Код | Что значит |
| --- | --- |
| 401 | ключа нет, он неверный, отозван или просрочен |
| 403 | у ключа нет права `ingest` |
| 413 | вложение больше лимита |
| 422 | тело не проходит валидацию (в `detail` — список полей) |

## Готовый клиент

```python
from thirdnews_contracts import IngestClient, NewsSubmission

client = IngestClient("https://news.example.edu", api_key="tnk_...")
client.submit(NewsSubmission(body_md="...", source_text="Деканат", external_id="1"))
```

См. также [руководство по написанию парсера](../guides/writing-a-parser.md).
