# Контракт выдачи новостей

Одна ручка на всех клиентов: сайт, бот, мобильное приложение, расширение.

```
GET /api/v1/news
```

## Авторизация

Принимается любой из способов, включённых в `NEWS_AUTH_BACKENDS`:

| Способ | Как передать |
| --- | --- |
| API-ключ | `X-API-Key: tnk_...` (или `Authorization: ApiKey tnk_...`, или `?api_key=`) |
| JWT | `Authorization: Bearer <jwt>` |
| Cookie-сессия | кука `news_session`, ставится через `POST /api/v1/auth/login` |

Токен для скриптов: `POST /api/v1/auth/token` с `{"email","password"}`.
Про добавление SSO — [`docs/auth.md`](../auth.md).

## Фильтры

Оси классификации создаются на ходу, поэтому фильтры по ним динамические:

```
GET /api/v1/news?facet.importance=critical,normal&facet.stream=2025
```

* значения **внутри одной оси** — ИЛИ;
* разные оси — И;
* список доступных осей и значений: `GET /api/v1/taxonomy`.

Остальные параметры:

| Параметр | Значение |
| --- | --- |
| `q` | подстрока в заголовке или тексте |
| `source` | slug источника, можно повторять |
| `status` | только для клиентов с правом `editor`; иначе отдаётся только `published` |
| `published_from` / `published_to` | по дате публикации в источнике (ISO 8601) |
| `received_from` / `received_to` | по времени прихода в сервис |
| `has_attachments` | `true` / `false` |
| `order` | `desc` (по умолчанию) или `asc` |
| `limit` | 1–200, по умолчанию 50 |
| `cursor` | из `next_cursor` предыдущей страницы |
| `with_total` | посчитать `total` (дороже, поэтому по запросу) |

Сортировка — по `published_at`, а если его нет, по `received_at`.

## Ответ

```json
{
  "items": [
    {
      "id": "9a1f…",
      "title": "…",
      "body_md": "…",
      "source_key": "tg-dekanat-fkn",
      "source_link": "https://t.me/…",
      "source_text": "Деканат ФКН, Telegram",
      "published_at": "2026-09-01T10:30:00Z",
      "received_at":  "2026-09-01T10:31:02Z",
      "lang": "ru",
      "status": "published",
      "labels": [
        { "facet": "importance", "facet_title": "Важность",
          "value": "critical", "value_title": "Очень важно",
          "origin": "manual", "confidence": 1.0 }
      ],
      "attachments": [
        { "id": "…", "kind": "image", "url": "/media/2026/09/ab12…_poster.jpg",
          "mime": "image/jpeg", "size": 148213, "caption": "Афиша", "position": 0 }
      ],
      "extra": {}
    }
  ],
  "next_cursor": "MjAyNi0wOS0wMV…",
  "total": null
}
```

`origin` показывает, откуда взялась метка (`manual`, `classifier`,
`source_default`, `parser`) — удобно, если клиент хочет доверять только ручной
разметке.

Пагинация — курсорная (keyset), поэтому новые новости не сдвигают страницы.
Идите по `next_cursor`, пока он не станет `null`.

## Ограничения на стороне ключа

У ключа может быть `filter_preset` — фильтры, которые сервер добавляет к любому
запросу:

```json
{ "facets": { "stream": ["2025"] }, "sources": ["tg-dekanat-fkn"] }
```

Такой ключ **не может** запросить ничего за пределами пресета: попытка сузиться
внутри него работает, попытка выйти наружу возвращает пустой результат. Это
позволяет выдать боту одного потока ключ, которым нельзя вычитать весь архив.

## Одна новость

```
GET /api/v1/news/{id}
```

Возвращает тот же объект. Неопубликованные новости для не-редакторов отдают 404
(а не 403 — чтобы не подтверждать существование черновика).
