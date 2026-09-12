// Страница показывает ленту так, как её видит клиент с ключом на чтение:
// ходит в те же /api/v1/feed и /api/v1/taxonomy, ничего административного.
// Ключ живёт в localStorage этого браузера и на сервер, кроме заголовка
// X-API-Key, не уходит.

const KEY_STORAGE = "thirdnews.preview.key";
const PAGE = 20;

const el = {
  key: document.getElementById("key"),
  save: document.getElementById("save"),
  q: document.getElementById("q"),
  sort: document.getElementById("sort"),
  withFiles: document.getElementById("withfiles"),
  reset: document.getElementById("reset"),
  facets: document.getElementById("facets"),
  count: document.getElementById("count"),
  list: document.getElementById("list"),
  more: document.getElementById("more"),
};

const state = {
  key: localStorage.getItem(KEY_STORAGE) || "",
  taxonomy: [],
  selected: new Map(), // ось -> Set значений
  counts: {},
  offset: 0,
  // Быстрые клики по фильтрам приходят не в том порядке, в каком уходили
  // запросы. Отрисовываем только ответ на самый свежий из них.
  sequence: 0,
};

el.key.value = state.key;

async function api(path) {
  const response = await fetch(path, { headers: { "X-API-Key": state.key } });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      /* тело может быть не JSON — сообщения статуса хватит */
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPES[char]);
}

// Полноценный markdown сюда не затащить: CSP страницы запрещает внешние
// скрипты. Разбираем то, что реально встречается в сообщениях TiMe.
function renderBody(markdown) {
  return escapeHtml(markdown)
    .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<i>$2</i>")
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" rel="noreferrer">$1</a>')
    .replace(/(^|\s)(https?:\/\/[^\s<]+)/g, '$1<a href="$2" rel="noreferrer">$2</a>');
}

function formatDate(value) {
  if (!value) return "без даты";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
}

function query(offset) {
  const params = new URLSearchParams();
  params.set("limit", String(PAGE));
  if (offset) params.set("cursor", String(offset));
  if (el.q.value.trim()) params.set("q", el.q.value.trim());
  params.set("sort", el.sort.value);
  if (el.withFiles.checked) params.set("has_attachments", "true");
  for (const [axis, values] of state.selected) {
    if (values.size) params.set(`facet.${axis}`, [...values].join(","));
  }
  return `/api/v1/feed?${params.toString()}`;
}

function drawFacets() {
  el.facets.replaceChildren();
  for (const facet of state.taxonomy) {
    const line = document.createElement("div");
    line.className = "axis";
    const name = document.createElement("b");
    name.textContent = facet.title;
    line.append(name);
    for (const value of facet.values) {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.type = "button";
      const active = state.selected.get(facet.slug)?.has(value.slug) ?? false;
      chip.setAttribute("aria-pressed", String(active));
      chip.textContent = value.title;
      const total = state.counts[`facets.${facet.slug}`]?.[value.slug];
      if (total !== undefined) {
        const badge = document.createElement("span");
        badge.className = "n";
        badge.textContent = String(total);
        chip.append(badge);
      }
      chip.addEventListener("click", () => {
        const chosen = state.selected.get(facet.slug) ?? new Set();
        if (chosen.has(value.slug)) chosen.delete(value.slug);
        else chosen.add(value.slug);
        if (chosen.size) state.selected.set(facet.slug, chosen);
        else state.selected.delete(facet.slug);
        load(true);
      });
      line.append(chip);
    }
    el.facets.append(line);
  }
}

// Картинки закрыты тем же ключом, что и лента, поэтому <img src> их не
// возьмёт: заголовок туда не поставить. Тянем запросом и подставляем data:
// — blob: страница запрещает своей же CSP.
const pictures = new Map();

async function showPicture(node, url) {
  if (!pictures.has(url)) {
    pictures.set(
      url,
      fetch(url, { headers: { "X-API-Key": state.key } })
        .then((response) => (response.ok ? response.blob() : Promise.reject(response.status)))
        .then(
          (blob) =>
            new Promise((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () => resolve(reader.result);
              reader.onerror = reject;
              reader.readAsDataURL(blob);
            }),
        ),
    );
  }
  try {
    node.src = await pictures.get(url);
  } catch {
    node.remove();
  }
}

const watcher = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      watcher.unobserve(entry.target);
      showPicture(entry.target, entry.target.dataset.src);
    }
  },
  { rootMargin: "300px" },
);

function drawItem(item) {
  const card = document.createElement("article");

  const title = document.createElement("h2");
  title.textContent = item.title || "(без заголовка)";
  card.append(title);

  const meta = document.createElement("div");
  meta.className = "meta";
  const parts = [formatDate(item.published_at), item.source_text || item.source || ""];
  if (item.importance !== null && item.importance !== undefined) {
    parts.push(`важность ${item.importance}`);
  }
  meta.textContent = parts.filter(Boolean).join(" · ");
  if (item.source_link) {
    meta.append(" · ");
    const link = document.createElement("a");
    link.href = item.source_link;
    link.rel = "noreferrer";
    link.textContent = "источник";
    meta.append(link);
  }
  card.append(meta);

  const body = document.createElement("div");
  body.className = "body";
  body.innerHTML = renderBody(item.body_md || "");
  card.append(body);

  const images = (item.attachments || []).filter((file) => file.kind === "image");
  const others = (item.attachments || []).filter((file) => file.kind !== "image");
  if (images.length) {
    const strip = document.createElement("div");
    strip.className = "shots";
    for (const file of images.slice(0, 4)) {
      const picture = document.createElement("img");
      picture.alt = file.filename || "вложение";
      picture.dataset.src = file.url;
      strip.append(picture);
      watcher.observe(picture);
    }
    card.append(strip);
  }
  if (others.length) {
    const files = document.createElement("div");
    files.className = "file";
    files.textContent = `вложения: ${others.map((file) => file.filename || file.kind).join(", ")}`;
    card.append(files);
  }

  if (item.labels?.length) {
    const labels = document.createElement("div");
    labels.className = "labels";
    for (const label of item.labels) {
      const tag = document.createElement("span");
      tag.className = "label";
      tag.textContent = `${label.facet_title}: ${label.value_title}`;
      labels.append(tag);
    }
    card.append(labels);
  }
  return card;
}

function showMessage(className, text) {
  el.count.replaceChildren();
  const message = document.createElement("div");
  message.className = className;
  message.textContent = text;
  el.count.append(message);
}

async function load(fresh) {
  if (!state.key) {
    el.list.replaceChildren();
    el.more.replaceChildren();
    showMessage("empty", "Введите ключ ленты и нажмите «запомнить».");
    return;
  }
  if (fresh) state.offset = 0;
  const ticket = ++state.sequence;
  el.count.textContent = "загружаю…";
  let page;
  try {
    page = await api(query(state.offset));
  } catch (error) {
    if (ticket !== state.sequence) return;
    el.list.replaceChildren();
    el.more.replaceChildren();
    showMessage("error", String(error.message));
    return;
  }
  if (ticket !== state.sequence) return;

  state.counts = page.facets || {};
  drawFacets();
  if (fresh) el.list.replaceChildren();
  for (const item of page.items || []) el.list.append(drawItem(item));

  const shown = el.list.childElementCount;
  if (page.total) {
    el.count.textContent = `${shown} из ${page.total}`;
  } else {
    showMessage(
      "empty",
      "Ничего не нашлось. Если новостей нет совсем — возможно, они ещё не опубликованы.",
    );
  }

  el.more.replaceChildren();
  if (page.next_cursor) {
    const button = document.createElement("button");
    button.textContent = "показать ещё";
    button.addEventListener("click", () => {
      state.offset = Number(page.next_cursor);
      load(false);
    });
    el.more.append(button);
  }
}

async function start() {
  if (!state.key) {
    load(true);
    return;
  }
  try {
    const taxonomy = await api("/api/v1/taxonomy");
    state.taxonomy = taxonomy.facets || [];
  } catch {
    state.taxonomy = [];
  }
  drawFacets();
  load(true);
}

el.save.addEventListener("click", () => {
  state.key = el.key.value.trim();
  localStorage.setItem(KEY_STORAGE, state.key);
  start();
});
el.reset.addEventListener("click", () => {
  state.selected.clear();
  el.q.value = "";
  el.withFiles.checked = false;
  el.sort.value = "published_at";
  start();
});
el.q.addEventListener("keydown", (event) => {
  if (event.key === "Enter") load(true);
});
el.sort.addEventListener("change", () => load(true));
el.withFiles.addEventListener("change", () => load(true));

start();
