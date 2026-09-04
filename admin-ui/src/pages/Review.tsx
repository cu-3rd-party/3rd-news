import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Facet, type NewsItem } from "../api";

const STATUSES = ["pending", "needs_review", "published", "rejected", "archived"];

/** The review queue: read the item, click the labels, publish. */
export function ReviewPage() {
  const [facets, setFacets] = useState<Facet[]>([]);
  const [items, setItems] = useState<NewsItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<string[]>(["pending", "needs_review"]);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const search = useMemo(() => {
    const params = new URLSearchParams();
    status.forEach((value) => params.append("status", value));
    if (query.trim()) params.set("q", query.trim());
    params.set("limit", "50");
    return `?${params.toString()}`;
  }, [status, query]);

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
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);

  async function act(id: string, action: () => Promise<unknown>) {
    setBusyId(id);
    try {
      await action();
      await reload();
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
      next = current.includes(valueSlug) ? [] : [valueSlug];
    } else {
      next = current.includes(valueSlug)
        ? current.filter((slug) => slug !== valueSlug)
        : [...current, valueSlug];
    }
    // Sending just this facet leaves the others to the classifiers.
    return act(item.id, () => api.setLabels(item.id, { [facet.slug]: next }));
  }

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
        <span className="muted">всего: {total}</span>
        <button onClick={() => void reload()}>Обновить</button>
      </div>

      {error && <p className="error">{error}</p>}

      {items.map((item) => (
        <article key={item.id} className="news">
          <header>
            <span className={`badge status-${item.status}`}>{item.status}</span>
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
            {facets.map((facet) => {
              const chosen = item.effective[facet.slug] ?? [];
              const isManual = item.manual_facets.includes(facet.slug);
              return (
                <div key={facet.id} className="facet">
                  <span className="facet-title">
                    {facet.title}
                    {isManual && <em title="закреплено вручную"> ✎</em>}
                  </span>
                  {facet.values.map((value) => (
                    <button
                      key={value.id}
                      className={chosen.includes(value.slug) ? "chip on" : "chip"}
                      disabled={busyId === item.id}
                      onClick={() => void toggleLabel(item, facet, value.slug)}
                    >
                      {value.title}
                    </button>
                  ))}
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
          </div>

          {item.opinions.length > 0 && (
            <details className="opinions">
              <summary>Кто что предложил ({item.opinions.length})</summary>
              <ul>
                {item.opinions.map((opinion, index) => (
                  <li key={index}>
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
            <button onClick={() => void act(item.id, () => api.setStatus(item.id, "published"))}>
              Опубликовать
            </button>
            <button onClick={() => void act(item.id, () => api.setStatus(item.id, "rejected"))}>
              Отклонить
            </button>
            <button onClick={() => void act(item.id, () => api.reclassify(item.id))}>
              Переклассифицировать
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
