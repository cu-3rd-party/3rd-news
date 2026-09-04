import { useCallback, useEffect, useState } from "react";
import { api, type ClassificationContext } from "../api";

/**
 * База знаний классификаторов.
 *
 * Две разные памяти. Здесь редактор пишет то, что модель не может вывести из
 * текста новости: расшифровки сокращений, названия потоков, кто такие
 * кураторы. Вторая половина — примеры ручной разметки — набирается сама,
 * из правок на вкладке «Новости», и здесь только показывается.
 */
export function KnowledgePage({ canEdit }: { canEdit: boolean }) {
  const [data, setData] = useState<ClassificationContext | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const context = await api.classificationContext();
      setData(context);
      setDraft(context.text);
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function save() {
    setBusy(true);
    setSaved(false);
    try {
      const context = await api.saveClassificationContext(draft);
      setData(context);
      setSaved(true);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return <div className="page">{error ? <p className="error">{error}</p> : <p className="muted">Загрузка…</p>}</div>;
  }

  const dirty = draft !== data.text;

  return (
    <div className="page">
      {error && <p className="error">{error}</p>}

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Что классификаторы знают об университете</h3>
        <p className="muted">
          Этот текст уходит в каждый запрос к классификатору. Без него «ВКР», «поток
          Восток» и «Fundamentals» для модели — незнакомые слова, и она додумывает их
          значение сама. Пишите простыми фразами: расшифровки, кто есть кто, что чем
          называется.
        </p>
        <textarea
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setSaved(false);
          }}
          disabled={!canEdit}
          rows={22}
          style={{ width: "100%", fontFamily: "inherit", lineHeight: 1.5 }}
        />
        <div className="row" style={{ marginTop: ".6rem" }}>
          {canEdit && (
            <button className="primary" disabled={busy || !dirty} onClick={() => void save()}>
              {busy ? "Сохраняю…" : "Сохранить"}
            </button>
          )}
          {dirty && <span className="muted">есть несохранённые правки</span>}
          {saved && <span className="ok">сохранено</span>}
          <span className="muted" style={{ marginLeft: "auto" }}>
            {draft.length} символов
          </span>
        </div>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Примеры ручной разметки</h3>
        <p className="muted" style={{ marginBottom: ".4rem" }}>
          Каждый раз, когда вы правите метки на вкладке «Новости», ваше решение
          попадает в следующие запросы к классификатору как образец. Это и есть
          обучение без обучения: чем больше правок, тем ближе разметка к вашим
          соглашениям.
        </p>
        <p style={{ margin: 0 }}>
          Сейчас набралось <strong>{data.example_count}</strong> из{" "}
          {data.examples_configured} запрошенных.
          {data.example_count === 0 && (
            <span className="muted">
              {" "}
              Пока ни одной — поправьте метки у пары новостей, и они появятся здесь.
            </span>
          )}
        </p>
      </section>
    </div>
  );
}
