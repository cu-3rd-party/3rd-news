      const $ = (id) => document.getElementById(id);
      const state = { offset: 0, limit: 50, total: 0, busy: false };

      
      
      let parserToken = "";
      const token = { get: () => parserToken, set: (value) => { parserToken = value; } };

      async function api(path, options = {}) {
        const headers = { ...(options.headers || {}) };
        if (token.get()) headers.Authorization = `Bearer ${token.get()}`;
        if (options.body) headers["Content-Type"] = "application/json";
        const response = await fetch(path, { ...options, headers });
        if (response.status === 401) {
          askToken();
          throw new Error("нужен токен парсера");
        }
        if (!response.ok) {
          let detail = response.statusText;
          try { detail = (await response.json()).detail ?? detail; } catch {}
          throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
        }
        return response.status === 204 ? null : response.json();
      }

      function askToken() {
        $("tokenInput").value = "";
        $("tokenDialog").showModal();
      }
      $("tokenDialog").addEventListener("close", () => {
        if ($("tokenDialog").returnValue === "save") {
          token.set($("tokenInput").value.trim());
          $("tokenInput").value = "";
          loadAll();
        }
      });
      $("settings").onclick = askToken;

      function fmtDate(iso) {
        if (!iso) return "—";
        return new Date(iso).toLocaleDateString("ru", { year: "numeric", month: "2-digit", day: "2-digit" });
      }

      function query(refresh = false) {
        const params = new URLSearchParams({
          limit: state.limit,
          offset: state.offset,
          sort: $("sort").value,
          only_with_posts: $("only_with_posts").checked,
          only_joined: $("only_joined").checked,
          only_selected: $("only_selected").checked,
        });
        if ($("q").value.trim()) params.set("q", $("q").value.trim());
        if ($("active").value) params.set("active_within_days", $("active").value);
        if (refresh) params.set("refresh", "true");
        return `/channels?${params}`;
      }

      async function loadChannels(refresh = false) {
        $("listStatus").textContent = refresh ? "Перечитываю из TiMe…" : "Загрузка…";
        $("listStatus").className = "muted";
        $("table").hidden = true;
        try {
          const data = await api(query(refresh));
          state.total = data.total;
          render(data.items);
          $("listStatus").hidden = data.items.length > 0;
          if (!data.items.length) {
            $("listStatus").hidden = false;
            $("listStatus").textContent = "Ничего не нашлось — ослабьте фильтры.";
          }
          $("table").hidden = data.items.length === 0;
          $("page").textContent = `${state.offset + 1}–${state.offset + data.items.length} из ${data.total}`;
          $("prev").disabled = state.offset === 0;
          $("next").disabled = state.offset + state.limit >= data.total;
        } catch (err) {
          $("listStatus").hidden = false;
          $("listStatus").textContent = err.message;
          $("listStatus").className = "error";
        }
      }

      function render(items) {
        $("rows").replaceChildren();
        for (const c of items) {
          const tr = document.createElement("tr");

          const tdCheck = document.createElement("td");
          const box = document.createElement("input");
          box.type = "checkbox";
          box.checked = c.selected;
          box.onchange = () => toggle(c, box);
          tdCheck.append(box);

          const tdName = document.createElement("td");
          const link = document.createElement("a");
          link.href = c.url;
          link.target = "_blank";
          link.rel = "noreferrer";
          link.textContent = c.display_name;
          link.className = "name";
          const slug = document.createElement("div");
          slug.className = "slug";
          slug.textContent = c.name + (c.purpose ? ` — ${c.purpose.slice(0, 70)}` : "");
          tdName.append(link, slug);

          const tdMsgs = document.createElement("td");
          tdMsgs.className = "num";
          tdMsgs.textContent = c.total_msg_count.toLocaleString("ru");

          const tdDate = document.createElement("td");
          tdDate.textContent = fmtDate(c.last_post_at);

          tr.append(tdCheck, tdName, tdMsgs, tdDate);
          $("rows").append(tr);
        }
      }

      async function toggle(channel, box) {
        box.disabled = true;
        const ref = `${channel.team}/${channel.name}`;
        try {
          if (box.checked) {
            await api("/channels/selected", { method: "POST", body: JSON.stringify({ channels: [ref] }) });
          } else {
            await api(`/channels/selected?channel=${encodeURIComponent(ref)}`, { method: "DELETE" });
          }
          channel.selected = box.checked;
          await loadSelected();
        } catch (err) {
          box.checked = !box.checked;
          alert(err.message);
        } finally {
          box.disabled = false;
        }
      }

      async function loadSelected() {
        try {
          const items = await api("/channels/selected");
          $("selected").replaceChildren();
          if (!items.length) {
            const empty = document.createElement("p");
            empty.className = "muted";
            empty.textContent = "Пока ничего. Отметьте каналы слева.";
            $("selected").append(empty);
            return;
          }
          for (const s of items) {
            const div = document.createElement("div");
            div.className = "selected-item";
            const run = s.last_run;
            const name = document.createElement("div");
            name.className = "name";
            name.textContent = s.display_name ?? s.channel;
            const slug = document.createElement("div");
            slug.className = "slug";
            slug.textContent = `${s.team}/${s.channel}`;
            const stats = document.createElement("div");
            stats.style.fontSize = ".9em";
            if (!run) {
              stats.className = "muted";
              stats.textContent = "ещё не запускался";
            } else if (run.error) {
              stats.className = "error";
              stats.textContent = `ошибка: ${String(run.error).slice(0, 80)}`;
            } else {
              const created = document.createElement("span");
              created.className = "ok";
              created.textContent = String(run.created);
              stats.append(created, document.createTextNode(
                ` новых, ${run.duplicates} были, ${run.skipped} мимо`
              ));
            }
            div.append(name, slug, stats);

            
            
            
            const modeWrap = document.createElement("label");
            modeWrap.className = "chip";
            modeWrap.title = "Снимите, если в канале объявления пишет обычный участник";
            const mode = document.createElement("input");
            mode.type = "checkbox";
            mode.checked = s.authors === "privileged";
            mode.onchange = async () => {
              mode.disabled = true;
              try {
                await api(`/channels/selected?channel=${encodeURIComponent(s.team + "/" + s.channel)}`
                          + `&authors=${mode.checked ? "privileged" : "all"}`, { method: "PATCH" });
              } catch (err) { mode.checked = !mode.checked; alert(err.message); }
              finally { mode.disabled = false; }
            };
            modeWrap.append(mode, document.createTextNode("только от тех, кому доверено"));
            div.append(modeWrap);
            const remove = document.createElement("button");
            remove.className = "link danger";
            remove.textContent = "убрать";
            remove.onclick = async () => {
              await api(`/channels/selected?channel=${encodeURIComponent(s.team + "/" + s.channel)}`, { method: "DELETE" });
              await Promise.all([loadSelected(), loadChannels()]);
            };
            div.append(remove);
            $("selected").append(div);
          }
        } catch (err) {
          const error = document.createElement("p");
          error.className = "error";
          error.textContent = err.message;
          $("selected").replaceChildren(error);
        }
      }

      async function runPoll(params = "") {
        if (state.busy) return;
        state.busy = true;
        $("poll").disabled = $("backfill").disabled = true;
        $("pollResult").className = "muted";
        $("pollResult").textContent = "Идёт прогон, это может занять минуты…";
        try {
          const data = await api(`/poll${params}`, { method: "POST" });
          const result = $("pollResult");
          result.className = "";
          result.replaceChildren();
          for (const [key, item] of Object.entries(data.results)) {
            if (result.childNodes.length) result.append(document.createElement("br"));
            const created = document.createElement("span");
            created.className = "ok";
            created.textContent = String(item.created);
            result.append(
              document.createTextNode(`${key}: `),
              created,
              document.createTextNode(` новых, ${item.duplicates} были`),
            );
          }
          if (!result.childNodes.length) {
            result.className = "muted";
            result.textContent = "Нечего парсить.";
          }
          await loadSelected();
        } catch (err) {
          $("pollResult").className = "error";
          $("pollResult").textContent = err.message;
        } finally {
          state.busy = false;
          $("poll").disabled = $("backfill").disabled = false;
        }
      }

      async function loadStatus() {
        try {
          const s = await api("/status");
          $("status").textContent = s.authorized
            ? `TiMe подключён · выбрано ${s.selected} · опрос раз в ${s.poll_interval_s}с`
            : "нет доступа к TiMe — проверьте TIME_COOKIE";
          $("status").className = s.authorized ? "muted" : "error";
        } catch (err) {
          $("status").textContent = err.message;
          $("status").className = "error";
        }
      }

      function loadAll() {
        loadStatus();
        loadSelected();
        loadChannels();
      }

      let timer;
      const debounce = () => { clearTimeout(timer); timer = setTimeout(() => { state.offset = 0; loadChannels(); }, 300); };
      $("q").oninput = debounce;
      for (const id of ["only_with_posts", "only_joined", "only_selected", "active", "sort"]) {
        $(id).onchange = () => { state.offset = 0; loadChannels(); };
      }
      $("prev").onclick = () => { state.offset = Math.max(0, state.offset - state.limit); loadChannels(); };
      $("next").onclick = () => { state.offset += state.limit; loadChannels(); };
      $("refresh").onclick = () => loadChannels(true);
      $("poll").onclick = () => runPoll();
      $("backfill").onclick = () => runPoll(`?max_age_days=${$("days").value}&max_pages=5`);

      loadAll();
