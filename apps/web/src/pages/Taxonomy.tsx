import { useCallback, useEffect, useState } from "react";
import { api, type Facet } from "../api";








export function TaxonomyPage({ canEdit }: { canEdit: boolean }) {
  const [facets, setFacets] = useState<Facet[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newFacet, setNewFacet] = useState({ title: "", type: "single", required: false });

  const reload = useCallback(async () => {
    try {
      setFacets(await api.facets());
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      await reload();
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="page">
      {error && <p className="error">{error}</p>}

      {canEdit && (
        <form
          className="row card"
          onSubmit={(event) => {
            event.preventDefault();
            if (!newFacet.title.trim()) return;
            void run(async () => {
              await api.createFacet(newFacet);
              setNewFacet({ title: "", type: "single", required: false });
            });
          }}
        >
          <input
            placeholder="Новая ось, напр. «Факультет»"
            value={newFacet.title}
            onChange={(e) => setNewFacet({ ...newFacet, title: e.target.value })}
          />
          <select
            value={newFacet.type}
            onChange={(e) => setNewFacet({ ...newFacet, type: e.target.value })}
          >
            <option value="single">одно значение</option>
            <option value="multi">несколько значений</option>
          </select>
          <label className="chip">
            <input
              type="checkbox"
              checked={newFacet.required}
              onChange={(e) => setNewFacet({ ...newFacet, required: e.target.checked })}
            />
            обязательная
          </label>
          <button>Добавить ось</button>
        </form>
      )}

      {facets.map((facet) => (
        <FacetCard key={facet.id} facet={facet} canEdit={canEdit} onChange={run} />
      ))}
    </div>
  );
}

function FacetCard({
  facet,
  canEdit,
  onChange,
}: {
  facet: Facet;
  canEdit: boolean;
  onChange: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [synonyms, setSynonyms] = useState("");

  return (
    <section className="card">
      <h3>
        {facet.title} <code>{facet.slug}</code>
        <span className="muted">
          {" "}
          · {facet.type === "single" ? "одно значение" : "несколько"}
          {facet.required && " · обязательная"}
        </span>
        {canEdit && (
          <button
            className="link danger"
            onClick={() => {
              if (confirm(`Удалить ось «${facet.title}» со всеми значениями?`)) {
                void onChange(() => api.deleteFacet(facet.id));
              }
            }}
          >
            удалить
          </button>
        )}
      </h3>

      <table>
        <thead>
          <tr>
            <th>Значение</th>
            <th>slug</th>
            <th>Ключевые слова (для regex-классификатора)</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {facet.values.map((value) => (
            <tr key={value.id}>
              <td>{value.title}</td>
              <td>
                <code>{value.slug}</code>
              </td>
              <td>
                <input
                  defaultValue={value.synonyms.join(", ")}
                  disabled={!canEdit}
                  onBlur={(event) => {
                    const next = event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean);
                    if (next.join(",") === value.synonyms.join(",")) return;
                    void onChange(() =>
                      api.updateValue(value.id, {
                        title: value.title,
                        description: value.description,
                        ai_hint: value.ai_hint,
                        synonyms: next,
                        match_patterns: value.match_patterns,
                        is_active: value.is_active,
                        position: value.position,
                      }),
                    );
                  }}
                />
              </td>
              <td>
                {canEdit && (
                  <button
                    className="link danger"
                    onClick={() => void onChange(() => api.deleteValue(value.id))}
                  >
                    ×
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {canEdit && (
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault();
            if (!title.trim()) return;
            void onChange(async () => {
              await api.createValue(facet.id, {
                title,
                synonyms: synonyms
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
              });
              setTitle("");
              setSynonyms("");
            });
          }}
        >
          <input
            placeholder="новое значение"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input
            placeholder="ключевые слова через запятую"
            value={synonyms}
            onChange={(e) => setSynonyms(e.target.value)}
          />
          <button>Добавить</button>
        </form>
      )}
    </section>
  );
}
