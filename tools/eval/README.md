# tools/eval — измеритель классификаторов

Меряет качество разметки по осям на золотом наборе — постах, размеченных
руками. Ядро и база для измерений не нужны: классификаторы импортируются по
пути и зовутся напрямую, как в `tests/conftest.py`.

## Входы

Лежат в `data/` (каталог в `.gitignore` — настоящие объявления в публичный
репозиторий не кладутся):

- `gold.jsonl` — `GET /api/v1/admin/news/export` (право `editor`). Одна
  строка на новость, только ручные метки, без `rejected`. Ключевое поле
  `manual_facets`: ось в списке с пустыми метками — «разметчик решил, что
  не применима»; ось не в списке — «не размечал», метрики по ней не считаются.
- `taxonomy.json` — `GET /api/v1/admin/facets` (с `ai_hint`, синонимами,
  паттернами).
- `context.md` — текст базы знаний (вкладка «База знаний»), необязателен.

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.edu","password":"..."}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
mkdir -p data
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/admin/news/export > data/gold.jsonl
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/admin/facets > data/taxonomy.json
```

Весь корпус без разметки (чтобы читать посты и придумывать оси) —
`?labelled=false`:

```bash
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/admin/news/export?labelled=false" > data/raw.jsonl
wc -l data/raw.jsonl
```

Промпт-эксперименты делаются правкой этих файлов, а не кода.

## Установка

```bash
pip install -r tools/eval/requirements.txt ./packages/contracts   # regex, метрики, каппа
pip install -r tools/eval/requirements-knn.txt                     # + sentence-transformers для kNN
export OPENROUTER_API_KEY=...                                       # для --classifier ai|combined
```

## Прогоны

Схема leave-one-out: каждый пост — тестовый, примеры для него берутся из
остальных, сам пост из своих примеров исключается.

```bash
python -m tools.eval run --data data/gold.jsonl --taxonomy data/taxonomy.json \
  --classifier regex --out results/regex.json
python -m tools.eval run --data data/gold.jsonl --taxonomy data/taxonomy.json --context data/context.md \
  --classifier ai --examples none --out results/ai-none.json
python -m tools.eval run ... --classifier ai --examples recent --k 8 --out results/ai-recent8.json
python -m tools.eval run ... --classifier ai --examples knn --k 5 --out results/ai-knn5.json
python -m tools.eval run ... --classifier combined --examples knn --k 5 --out results/combined-knn5.json
python -m tools.eval compare results/*.json
```

- `--classifier`: `regex` — словарь из админки; `ai` — LLM через OpenRouter
  (`--model` переопределяет модель); `combined` — прод-правило: regex
  сильнее LLM по той же оси, пороги `--regex-threshold`/`--ai-threshold`.
- `--examples`: `none`, `recent` (как сейчас в ядре — k самых свежих) или
  `knn` (k ближайших по эмбеддингам `intfloat/multilingual-e5-base`;
  `--embedder fake` — мешок слов без torch, для проверки самой схемы).
- `--only-gold` — тест только по `is_gold`, пул примеров — всё остальное.

Ответы LLM кэшируются в `data/cache/llm/` по хэшу промпта, векторы — в
`data/cache/emb/`. Смена порога или метрики денег не стоит, смена промпта
или примеров — стоит.

Отчёт по каждой оси: `exact` (доля постов, где множество меток совпало
целиком; для single-оси это accuracy), `macroF1`, precision/recall/F1 по
значениям, калибровка уверенности по корзинам, токены и латентность.

## Второй разметчик

```bash
python -m tools.eval blind --data data/gold.jsonl --taxonomy data/taxonomy.json --n 100 --out data/blind.csv
# друг заполняет колонки осей: пусто — не размечал, '-' — нет значения, 'a;b' — несколько
python -m tools.eval kappa --data data/gold.jsonl --taxonomy data/taxonomy.json --other data/friend.csv
```

Каппа Коэна ниже 0.6 по оси означает, что определение не работает: править
инструкцию разметчика, а не модель. Расхождения печатаются списком —
разбирать вдвоём, эталон править в админке и экспортировать заново.
