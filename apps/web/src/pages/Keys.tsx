import { useCallback, useEffect, useState } from "react";
import { api, type ApiKey, type Source } from "../api";

const SCOPES = ["read", "ingest", "editor", "admin"];


export function KeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [issued, setIssued] = useState<string | null>(null);
  const [draft, setDraft] = useState({
    name: "",
    scopes: ["read"] as string[],
    source_id: "",
  });

  const reload = useCallback(async () => {
    try {
      const [keyList, sourceList] = await Promise.all([api.apiKeys(), api.sources()]);
      setKeys(keyList);
      setSources(sourceList);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) return;
    try {
      const result = await api.createApiKey({
        name: draft.name,
        scopes: draft.scopes,
        source_id: draft.source_id || null,
      });
      
      setIssued(result.secret);
      setDraft({ name: "", scopes: ["read"], source_id: "" });
      await reload();
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="page">
      {error && <p className="error">{error}</p>}

      {issued && (
        <div className="card highlight">
          <p>
            Ключ создан. Скопируйте его сейчас — сервер хранит только хэш и больше не
            покажет значение:
          </p>
          <code className="secret">{issued}</code>
          <button onClick={() => setIssued(null)}>Понятно</button>
        </div>
      )}

      <form className="row card" onSubmit={create}>
        <input
          placeholder="Название, напр. «парсер ТГ деканата»"
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
        {SCOPES.map((scope) => (
          <label key={scope} className="chip">
            <input
              type="checkbox"
              checked={draft.scopes.includes(scope)}
              onChange={() =>
                setDraft((prev) => ({
                  ...prev,
                  scopes: prev.scopes.includes(scope)
                    ? prev.scopes.filter((item) => item !== scope)
                    : [...prev.scopes, scope],
                }))
              }
            />
            {scope}
          </label>
        ))}
        <select
          value={draft.source_id}
          onChange={(e) => setDraft({ ...draft, source_id: e.target.value })}
        >
          <option value="">без привязки к источнику</option>
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.title}
            </option>
          ))}
        </select>
        <button>Выпустить ключ</button>
      </form>

      <table className="card">
        <thead>
          <tr>
            <th>Название</th>
            <th>Префикс</th>
            <th>Права</th>
            <th>Последнее использование</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => (
            <tr key={key.id} className={key.is_active ? "" : "muted"}>
              <td>{key.name}</td>
              <td>
                <code>{key.prefix}…</code>
              </td>
              <td>{key.scopes.join(", ")}</td>
              <td className="muted">
                {key.last_used_at ? new Date(key.last_used_at).toLocaleString("ru") : "—"}
              </td>
              <td>
                {key.is_active ? (
                  <button
                    className="link danger"
                    onClick={() => {
                      if (confirm(`Отозвать ключ «${key.name}»?`)) {
                        void api.revokeApiKey(key.id).then(reload).catch((e) => setError(String(e)));
                      }
                    }}
                  >
                    отозвать
                  </button>
                ) : (
                  <span className="muted">отозван</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
