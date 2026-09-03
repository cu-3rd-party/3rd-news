import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Me } from "./api";
import { ReviewPage } from "./pages/Review";
import { TaxonomyPage } from "./pages/Taxonomy";
import { SourcesPage } from "./pages/Sources";
import { KeysPage } from "./pages/Keys";
import { ClassifiersPage } from "./pages/Classifiers";

type Tab = "review" | "taxonomy" | "sources" | "keys" | "classifiers";

const TABS: { id: Tab; label: string; adminOnly?: boolean }[] = [
  { id: "review", label: "Новости" },
  { id: "taxonomy", label: "Классификация" },
  { id: "sources", label: "Источники" },
  { id: "keys", label: "API-ключи", adminOnly: true },
  { id: "classifiers", label: "Классификаторы", adminOnly: true },
];

function LoginForm({ onLogin }: { onLogin: (me: Me) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(email, password));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <h1>3rd-news</h1>
      <label>
        Email
        <input value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
      </label>
      <label>
        Пароль
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button disabled={busy}>{busy ? "..." : "Войти"}</button>
    </form>
  );
}

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("review");

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, []);

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    setMe(null);
  }, []);

  if (loading) return <p className="centered">Загрузка...</p>;
  if (!me) return <LoginForm onLogin={setMe} />;

  const isAdmin = me.scopes.includes("admin");
  const visible = TABS.filter((entry) => !entry.adminOnly || isAdmin);

  return (
    <div className="app">
      <header>
        <strong>3rd-news</strong>
        <nav>
          {visible.map((entry) => (
            <button
              key={entry.id}
              className={tab === entry.id ? "active" : ""}
              onClick={() => setTab(entry.id)}
            >
              {entry.label}
            </button>
          ))}
        </nav>
        <span className="who">
          {me.display_name} ({me.role ?? me.kind})
          <button onClick={logout}>Выйти</button>
        </span>
      </header>
      <main>
        {tab === "review" && <ReviewPage />}
        {tab === "taxonomy" && <TaxonomyPage canEdit={isAdmin} />}
        {tab === "sources" && <SourcesPage canEdit={isAdmin} />}
        {tab === "keys" && <KeysPage />}
        {tab === "classifiers" && <ClassifiersPage />}
      </main>
    </div>
  );
}
