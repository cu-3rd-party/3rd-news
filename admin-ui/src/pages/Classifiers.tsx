import { useCallback, useEffect, useState } from "react";
import { api, type Classifier } from "../api";

/**
 * Registering a classification service.
 *
 * There is nothing special about the two that ship with this repo — anything
 * reachable over HTTP that answers `GET /manifest` and `POST /classify` can be
 * added here, including a service in somebody else's repository.
 */
export function ClassifiersPage() {
  const [items, setItems] = useState<Classifier[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [probe, setProbe] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState({
    name: "",
    base_url: "",
    secret: "",
    priority: 100,
    min_confidence: 0.6,
    auto_apply: true,
    timeout_s: 30,
  });

  const reload = useCallback(async () => {
    try {
      setItems(await api.classifiers());
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

      <form
        className="row card"
        onSubmit={(event) => {
          event.preventDefault();
          if (!draft.name.trim() || !draft.base_url.trim()) return;
          void run(async () => {
            await api.createClassifier({ ...draft, facets: [], config: {} });
            setDraft({ ...draft, name: "", base_url: "", secret: "" });
          });
        }}
      >
        <input
          placeholder="Название"
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
        <input
          placeholder="http://classifier-regex:8000"
          value={draft.base_url}
          onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
        />
        <input
          placeholder="общий секрет (HMAC)"
          value={draft.secret}
          onChange={(e) => setDraft({ ...draft, secret: e.target.value })}
        />
        <label>
          приоритет
          <input
            type="number"
            value={draft.priority}
            onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) })}
          />
        </label>
        <label>
          мин. уверенность
          <input
            type="number"
            step="0.05"
            min="0"
            max="1"
            value={draft.min_confidence}
            onChange={(e) => setDraft({ ...draft, min_confidence: Number(e.target.value) })}
          />
        </label>
        <button>Зарегистрировать</button>
      </form>

      {items.map((item) => (
        <section key={item.id} className="card">
          <h3>
            {item.name} <code>{item.slug}</code>
            <span className="muted">
              {" "}
              · приоритет {item.priority} · порог {item.min_confidence}
              {item.has_secret ? " · подписан" : " · без подписи"}
            </span>
          </h3>
          <p className="muted">{item.base_url}</p>

          <div className="row">
            <label className="chip">
              <input
                type="checkbox"
                checked={item.is_active}
                onChange={(e) =>
                  void run(() =>
                    api.updateClassifier(item.id, { ...item, is_active: e.target.checked }),
                  )
                }
              />
              включён
            </label>
            <label className="chip" title="Выключите, чтобы предложения только сохранялись">
              <input
                type="checkbox"
                checked={item.auto_apply}
                onChange={(e) =>
                  void run(() =>
                    api.updateClassifier(item.id, { ...item, auto_apply: e.target.checked }),
                  )
                }
              />
              применять автоматически
            </label>
            <button
              onClick={() =>
                void api
                  .probeClassifier(item.id)
                  .then((result) =>
                    setProbe((prev) => ({
                      ...prev,
                      [item.id]: result.ok
                        ? `OK: ${JSON.stringify(result.manifest)}`
                        : `ошибка: ${result.error}`,
                    })),
                  )
                  .catch((err) => setError(String(err)))
              }
            >
              Проверить связь
            </button>
            <button
              className="link danger"
              onClick={() => {
                if (confirm(`Удалить «${item.name}»?`)) {
                  void run(() => api.deleteClassifier(item.id));
                }
              }}
            >
              удалить
            </button>
          </div>

          {probe[item.id] && <pre className="probe">{probe[item.id]}</pre>}
          {item.last_error && (
            <p className="error">
              последняя ошибка ({item.last_error_at}): {item.last_error}
            </p>
          )}
        </section>
      ))}

      {items.length === 0 && (
        <p className="muted">
          Классификаторов нет — новости будут ждать ручной разметки.
        </p>
      )}
    </div>
  );
}
