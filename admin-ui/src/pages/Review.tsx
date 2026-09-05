import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Facet, type NewsItem, type Source } from "../api";

const STATUSES = ["pending", "needs_review", "published", "rejected", "archived"];
const PAGE_SIZES = [25, 50, 100, 200];

/**
 * Очередь ревью: прочитать, проставить метки, опубликовать.
 *
 * Размечать сотни постов мышкой невозможно, поэтому здесь есть активный пост и
 * активная ось: цифры выбирают значение, Tab переключает ось, Enter уводит к
 * следующему посту. После выбора значения на одиночной оси фокус сам уходит на
 * следующую — типовой пост размечается четырьмя нажатиями.
 */
export function ReviewPage() {
  const [facets, setFacets] = useState<Facet[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [items, setItems] = useState<NewsItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<string[]>(["pending", "needs_review"]);
  const [query, setQuery] = useState("");
  const [gold, setGold] = useState<"" | "true" | "false">("");
  const [source, setSource] = useState("");
  const [unlabelled, setUnlabelled] = useState("");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const [activeFacet, setActiveFacet] = useState(0);
  const [showHelp, setShowHelp] = useState(false);
  const itemRefs = useRef<(HTMLElement | null)[]>([]);

  /**
   * Выключенные оси и значения остаются в админском ответе (их можно вернуть),
   * но размечать по ним нельзя — и, что важнее, они сдвигали бы нумерацию
   * клавиш относительно того, что человек видит на экране.
   */
  const active_facets = useMemo(
    () =>
      facets
        .filter((facet) => facet.is_active)
        .map((facet) => ({ ...facet, values: facet.values.filter((value) => value.is_active) })),
    [facets],
  );

  /**
   * Оси, которые заполняет источник (`default_labels` канала): направление
   * программы приходит из канала, а не из текста. Руками их ставить нельзя —
   * ручная метка перебьёт источник и разъедется с остальными копиями. Список
   * берём из самих источников, а не зашиваем slug в код.
   */
  const sourceDriven = useMemo(
    () => new Set(sources.flatMap((item) => Object.keys(item.default_labels ?? {}))),
    [sources],
  );

  /** Оси, которые размечает человек, — по ним же нумеруются клавиши. */
  const shown = useMemo(
    () => active_facets.filter((facet) => !sourceDriven.has(facet.slug)),
    [active_facets, sourceDriven],
  );

  const search = useMemo(() => {
    const params = new URLSearchParams();
    status.forEach((value) => params.append("status", value));
    if (query.trim()) params.set("q", query.trim());
    if (gold) params.set("gold", gold);
    if (source) params.set("source", source);
    if (unlabelled) params.set("unlabelled_facet", unlabelled);
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    return `?${params.toString()}`;
  }, [status, query, gold, source, unlabelled, limit, offset]);

  const reload = useCallback(async () => {
    try {
      const page = await api.news(search);
      setItems(page.items);
      setTotal(page.total);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }, [search]);

  useEffect(() => {
    api.facets().then(setFacets).catch(() => undefined);
    api.sources().then(setSources).catch(() => undefined);
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);

  // Смена фильтров возвращает на первую страницу: иначе легко оказаться на
  // пустом «пятом экране» выборки, в которой теперь двадцать постов.
  useEffect(() => {
    setOffset(0);
  }, [status, query, gold, source, unlabelled, limit]);

  // Курсор сбрасывается при смене выборки, но не при обновлении одного поста:
  // иначе каждая проставленная метка отбрасывала бы разметчика к первой оси
  // первого поста.
  useEffect(() => {
    setActive(0);
    setActiveFacet(0);
  }, [search]);

  useEffect(() => {
    setActive((prev) => Math.min(prev, Math.max(0, items.length - 1)));
  }, [items.length]);

  useEffect(() => {
    itemRefs.current[active]?.scrollIntoView({ block: "nearest" });
  }, [active]);

  /** Обновляет один пост на месте: перезагружать страницу после каждой метки
   *  слишком дорого и сбивает позицию. */
  function replace(item: NewsItem) {
    setItems((prev) => prev.map((old) => (old.id === item.id ? item : old)));
  }

  async function act(id: string, action: () => Promise<unknown>, refresh = false) {
    setBusyId(id);
    try {
      const result = await action();
      if (refresh) await reload();
      else if (result && typeof result === "object" && "id" in result) {
        replace(result as NewsItem);
      }
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusyId(null);
    }
  }

  function toggleLabel(item: NewsItem, facet: Facet, valueSlug: string) {
    const current = item.effective[facet.slug] ?? [];
    let next: string[];
    if (facet.type === "single") {
      // Одиночная ось не переключается кликом: нажатие на уже выбранное
      // значение — это подтверждение, а не отмена. Иначе «поставить то же
      // самое» молча превращалось в «ось не применима», и разметчик получал
      // «нет значения» там, где выбирал нормальное.
      next = [valueSlug];
    } else {
      next = current.includes(valueSlug)
        ? current.filter((slug) => slug !== valueSlug)
        : [...current, valueSlug];
    }
    // Sending just this facet leaves the others to the classifiers.
    return act(item.id, () => api.setLabels(item.id, { [facet.slug]: next }));
  }

  // Обработчик клавиш вешается один раз и читает состояние через ref: если
  // пересоздавать его на каждое изменение, быстрый набор попадает в уже
  // устаревшее замыкание и метка уезжает не на ту ось.
  const cursor = useRef({ items, active, activeFacet, facets: shown });
  cursor.current = { items, active, activeFacet, facets: shown };

  /** Двигает курсор и в ref, и в состоянии — см. комментарий в `pick`. */
  const moveTo = useCallback((post: number, facet: number) => {
    cursor.current.active = post;
    cursor.current.activeFacet = facet;
    setActive(post);
    setActiveFacet(facet);
  }, []);

  const pick = useCallback((index: number) => {
    const { items: list, active: at, activeFacet: facetAt, facets: axes } = cursor.current;
    const item = list[at];
    const facet = axes[facetAt];
    if (!item || !facet) return;

    if (index === facet.values.length) {
      void act(item.id, () => api.setLabels(item.id, { [facet.slug]: [] }));
    } else {
      const value = facet.values[index];
      if (!value) return;
      void toggleLabel(item, facet, value.slug);
    }
    // Одиночная ось закрыта одним нажатием — сразу к следующей. Курсор в ref
    // двигаем тут же: два нажатия подряд попадают в один кадр, рендера между
    // ними нет, и вторая цифра иначе ушла бы на ту же ось.
    if (facet.type === "single" && facetAt < axes.length - 1) {
      cursor.current.activeFacet = facetAt + 1;
      setActiveFacet(facetAt + 1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const { items: list, active: at, activeFacet: facetAt, facets: axes } = cursor.current;
      const item = list[at];

      if (event.key >= "1" && event.key <= "9") {
        pick(Number(event.key) - 1);
      } else if (event.key === "0") {
        const facet = axes[facetAt];
        if (facet) pick(facet.values.length);
      } else if (event.key === "Tab") {
        if (axes.length === 0) return;
        const next = event.shiftKey
          ? (facetAt - 1 + axes.length) % axes.length
          : (facetAt + 1) % axes.length;
        moveTo(at, next);
      } else if (event.key === "Enter" || event.key === "j" || event.key === "ArrowDown") {
        moveTo(Math.min(at + 1, list.length - 1), 0);
      } else if (event.key === "k" || event.key === "ArrowUp") {
        moveTo(Math.max(at - 1, 0), 0);
      } else if (event.key === "g" && item) {
        void act(item.id, () => api.setGold([item.id], !item.is_gold), true);
      } else if (event.key === "x" && item) {
        void act(item.id, () => api.setStatus(item.id, "rejected"), true);
      } else if (event.key === "?") {
        setShowHelp((prev) => !prev);
      } else {
        return;
      }
      event.preventDefault();
    }

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pick, moveTo, search]);

  const firstShown = items.length === 0 ? 0 : offset + 1;

  return (
    <div className="page">
      <div className="toolbar">
        {STATUSES.map((value) => (
          <label key={value} className="chip">
            <input
              type="checkbox"
              checked={status.includes(value)}
              onChange={() =>
                setStatus((prev) =>
                  prev.includes(value) ? prev.filter((s) => s !== value) : [...prev, value],
                )
              }
            />
            {value}
          </label>
        ))}
        <input
          placeholder="поиск по тексту"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={source} onChange={(e) => setSource(e.target.value)} title="Канал">
          <option value="">все каналы</option>
          {sources.map((item) => (
            <option key={item.id} value={item.slug}>
              {item.title}
            </option>
          ))}
        </select>
        <select
          value={unlabelled}
          onChange={(e) => setUnlabelled(e.target.value)}
          title="Показать только те, где эта ось ещё не размечена"
        >
          <option value="">любая размеченность</option>
          {shown.map((facet) => (
            <option key={facet.id} value={facet.slug}>
              без «{facet.title}»
            </option>
          ))}
        </select>
        <select
          value={gold}
          onChange={(e) => setGold(e.target.value as "" | "true" | "false")}
          title="Золотые — эталон для измерителя классификаторов"
        >
          <option value="">все</option>
          <option value="true">только золотые</option>
          <option value="false">без золотых</option>
        </select>
        <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} title="На странице">
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              по {size}
            </option>
          ))}
        </select>
        <button onClick={() => void reload()}>Обновить</button>
        <button className="link" onClick={() => setShowHelp((prev) => !prev)}>
          клавиши (?)
        </button>
      </div>

      <div className="toolbar">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
          ← назад
        </button>
        <span className="muted">
          {firstShown}–{offset + items.length} из {total}
        </span>
        <button
          disabled={offset + items.length >= total}
          onClick={() => setOffset(offset + limit)}
        >
          вперёд →
        </button>
      </div>

      {showHelp && (
        <div className="help">
          <p>
            <code>1…9</code> — значение активной оси, <code>0</code> — «нет значения»,{" "}
            <code>Tab</code> — следующая ось (<code>Shift+Tab</code> — предыдущая),{" "}
            <code>Enter</code> / <code>j</code> — следующий пост, <code>k</code> — предыдущий,{" "}
            <code>g</code> — в золото, <code>x</code> — отклонить, <code>?</code> — эта справка.
          </p>
          <p className="muted">
            После выбора на одиночной оси фокус сам переходит на следующую, поэтому
            типовой пост размечается как <code>3 1 2 4 Enter</code>.
          </p>
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {items.map((item, index) => (
        <article
          key={item.id}
          ref={(node) => {
            itemRefs.current[index] = node;
          }}
          className={index === active ? "news active" : "news"}
          onClick={() => setActive(index)}
        >
          <header>
            <span className={`badge status-${item.status}`}>{item.status}</span>
            {item.is_gold && (
              <span className="badge gold" title="эталон для измерителя классификаторов">
                золото
              </span>
            )}
            <strong>{item.title ?? "(без заголовка)"}</strong>
            <span className="muted">
              {item.source_key ?? item.source_text ?? "—"} ·{" "}
              {new Date(item.published_at ?? item.received_at).toLocaleString("ru")}
            </span>
            {item.source_link && (
              <a href={item.source_link} target="_blank" rel="noreferrer">
                оригинал
              </a>
            )}
          </header>

          <pre className="body">{item.body_md}</pre>

          {item.attachments.length > 0 && (
            <div className="attachments">
              {item.attachments.map((file) => (
                <a key={file.id} href={file.url ?? "#"} target="_blank" rel="noreferrer">
                  {file.kind}: {file.filename ?? file.url}
                  {file.status !== "stored" && <em> ({file.status})</em>}
                </a>
              ))}
            </div>
          )}

          <div className="facets">
            {shown.map((facet, facetIndex) => {
              const chosen = item.effective[facet.slug] ?? [];
              const isManual = item.manual_facets.includes(facet.slug);
              const isActive = index === active && facetIndex === activeFacet;
              return (
                <div key={facet.id} className={isActive ? "facet active" : "facet"}>
                  <span className="facet-title">
                    {facet.title}
                    {isManual && <em title="закреплено вручную"> ✎</em>}
                  </span>
                  {facet.values.map((value, valueIndex) => (
                    <button
                      key={value.id}
                      /* Подсказка классификатора и решение человека выглядели
                         одинаково, и было не видно, что ось ещё не размечена. */
                      className={
                        chosen.includes(value.slug)
                          ? isManual
                            ? "chip on"
                            : "chip suggested"
                          : "chip"
                      }
                      disabled={busyId === item.id}
                      onClick={() => void toggleLabel(item, facet, value.slug)}
                    >
                      {isActive && valueIndex < 9 && <b>{valueIndex + 1} </b>}
                      {value.title}
                    </button>
                  ))}
                  {/* «Ось не применима» — тоже решение, и его надо зафиксировать
                      явно, иначе «пусто» не отличить от «не размечал». */}
                  <button
                    className={isManual && chosen.length === 0 ? "chip on" : "chip"}
                    disabled={busyId === item.id}
                    title="Ось не применима к этой новости"
                    onClick={() =>
                      void act(item.id, () => api.setLabels(item.id, { [facet.slug]: [] }))
                    }
                  >
                    {isActive && <b>0 </b>}
                    нет значения
                  </button>
                  {isManual && (
                    <button
                      className="link"
                      onClick={() =>
                        void act(item.id, () => api.setLabels(item.id, {}, [facet.slug]))
                      }
                    >
                      вернуть авто
                    </button>
                  )}
                </div>
              );
            })}

            {/* Оси от источника показываем, но не даём трогать: ручная метка
                перебила бы канал и разъехалась бы с копиями объявления. */}
            {active_facets
              .filter((facet) => sourceDriven.has(facet.slug))
              .map((facet) => {
                const chosen = item.effective[facet.slug] ?? [];
                const titles = facet.values
                  .filter((value) => chosen.includes(value.slug))
                  .map((value) => value.title);
                const pinned = item.manual_facets.includes(facet.slug);
                return (
                  <div key={facet.id} className="facet from-source">
                    <span className="facet-title">{facet.title}</span>
                    <span className="muted">{titles.join(", ") || "—"} (из канала)</span>
                    {pinned && (
                      <button
                        className="link"
                        title="Ось заполняется источником; ручная метка её перебивает"
                        onClick={() =>
                          void act(item.id, () => api.setLabels(item.id, {}, [facet.slug]))
                        }
                      >
                        снять ручную метку
                      </button>
                    )}
                  </div>
                );
              })}
          </div>

          {item.opinions.length > 0 && (
            <details className="opinions">
              <summary>Кто что предложил ({item.opinions.length})</summary>
              <ul>
                {item.opinions.map((opinion, opinionIndex) => (
                  <li key={opinionIndex}>
                    <code>
                      {opinion.facet}={opinion.value}
                    </code>{" "}
                    — {opinion.origin}
                    {opinion.origin_key && `:${opinion.origin_key}`} (
                    {opinion.confidence.toFixed(2)})
                    {opinion.reason && <span className="muted"> — {opinion.reason}</span>}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <footer>
            <button
              onClick={() => void act(item.id, () => api.setStatus(item.id, "published"), true)}
            >
              Опубликовать
            </button>
            <button
              onClick={() => void act(item.id, () => api.setStatus(item.id, "rejected"), true)}
            >
              Отклонить
            </button>
            <button onClick={() => void act(item.id, () => api.reclassify(item.id), true)}>
              Переклассифицировать
            </button>
            <button
              className="link"
              title="Золотые новости не отдаются классификаторам как примеры"
              onClick={() => void act(item.id, () => api.setGold([item.id], !item.is_gold), true)}
            >
              {item.is_gold ? "снять золото" : "в золото"}
            </button>
          </footer>
        </article>
      ))}

      {items.length === 0 && (
        <p className="muted">
          Ничего не найдено.
          {!status.includes("published") && (
            <>
              {" "}
              Если новости приходят, но очередь пуста — скорее всего они уже
              опубликованы автоматически (`NEWS_AUTO_PUBLISH`). Включите фильтр{" "}
              <code>published</code>.
            </>
          )}
        </p>
      )}
    </div>
  );
}
