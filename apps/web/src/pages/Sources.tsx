import { useCallback, useEffect, useState } from "react";
import { api, type Source } from "../api";


export function SourcesPage({ canEdit }: { canEdit: boolean }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({ title: "", kind: "telegram", url: "" });

  const reload = useCallback(async () => {
    try {
      setSources(await api.sources());
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
            if (!draft.title.trim()) return;
            void run(async () => {
              await api.createSource(draft);
              setDraft({ title: "", kind: "telegram", url: "" });
            });
          }}
        >
          <input
            placeholder="Название канала"
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
          <select
            value={draft.kind}
            onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
          >
            {["telegram", "vk", "rss", "site", "manual", "other"].map((kind) => (
              <option key={kind}>{kind}</option>
            ))}
          </select>
          <input
            placeholder="URL"
            value={draft.url}
            onChange={(e) => setDraft({ ...draft, url: e.target.value })}
          />
          <button>Добавить источник</button>
        </form>
      )}

      <table className="card">
        <thead>
          <tr>
            <th>Название</th>
            <th>slug</th>
            <th>Тип</th>
            <th>Последняя новость</th>
            <th>Классификация</th>
            <th>Активен</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.id}>
              <td>{source.title}</td>
              <td>
                <code>{source.slug}</code>
              </td>
              <td>{source.kind}</td>
              <td className="muted">
                {source.last_ingest_at
                  ? new Date(source.last_ingest_at).toLocaleString("ru")
                  : "—"}
              </td>
              <td>
                <label className="chip">
                  <input
                    type="checkbox"
                    disabled={!canEdit}
                    checked={!source.skip_classification}
                    onChange={(event) =>
                      void run(() =>
                        api.updateSource(source.id, {
                          ...source,
                          skip_classification: !event.target.checked,
                        }),
                      )
                    }
                  />
                  авто
                </label>
              </td>
              <td>
                <label className="chip">
                  <input
                    type="checkbox"
                    disabled={!canEdit}
                    checked={source.is_active}
                    onChange={(event) =>
                      void run(() =>
                        api.updateSource(source.id, {
                          ...source,
                          is_active: event.target.checked,
                        }),
                      )
                    }
                  />
                </label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {sources.length === 0 && <p className="muted">Источников пока нет.</p>}
    </div>
  );
}
