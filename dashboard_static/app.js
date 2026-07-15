(function () {
  // ===================== Config =====================
  const API_BASE = ""; // Routes are at /reports, /sop, etc.

  // ===================== Utilities =====================
  const el = (id) => document.getElementById(id);
  const todayISO = () => new Date().toISOString().slice(0, 10);
  function weekStartISO() {
    const d = new Date();
    const day = d.getDay(); // 0 Sun..6 Sat
    const diff = day === 0 ? -6 : 1 - day; // Monday start
    const s = new Date(d);
    s.setDate(d.getDate() + diff);
    return s.toISOString().slice(0, 10);
  }
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[m]));
  }
  function typeBadge(t) {
    const map = { insight: "INSIGHT", sop: "SOP", summary: "SUMMARY", report: "REPORT", event: "EVENT" };
    const label = map[(t || "").toLowerCase()] || (t ? String(t).toUpperCase() : "ITEM");
    return `<span class="badge">${escapeHtml(label)}</span>`;
  }
  function parseTsToMs(ts) {
    if (!ts && ts !== 0) return null;
    if (typeof ts === "number") return String(ts).length <= 10 ? ts * 1000 : ts;
    const d = new Date(ts);
    return isNaN(d) ? null : d.getTime();
  }
  function dayBoundsMs(dateISO) {
    const d = new Date(dateISO + "T00:00:00");
    const start = d.getTime();
    const end = start + 24 * 60 * 60 * 1000 - 1;
    return [start, end];
  }
  function rangeBoundsMs(startISO, endISO) {
    const [s] = dayBoundsMs(startISO);
    const [, e] = dayBoundsMs(endISO);
    return [s, e];
  }
  function inMsRange(ms, startMs, endMs) {
    return ms != null && ms >= startMs && ms <= endMs;
  }

  // ===================== Token (Settings) =====================
  function getToken() {
    return localStorage.getItem("dash_token") || "";
  }
  function authHeaders(extra = {}) {
    return { "X-Auth-Token": getToken() || "demo", ...extra };
  }
  function setToken(val) {
    localStorage.setItem("dash_token", val || "");
  }
  function wireSettings() {
    const input = el("token-input");
    const saveBtn = el("token-save-btn");
    const status = el("token-status");
    if (!input || !saveBtn) return;

    input.value = getToken();
    saveBtn.addEventListener("click", () => {
      setToken(input.value.trim());
      if (status) {
        status.textContent = "Token saved for this browser.";
        setTimeout(() => (status.textContent = ""), 2000);
      }
    });
  }

  // ===================== View switching =====================
  function showView(name) {
    document.querySelectorAll("[data-view]").forEach((s) => s.classList.add("hidden"));
    const active = document.querySelector(`[data-view="${name}"]`);
    if (active) active.classList.remove("hidden");

    document.querySelectorAll(".nav [data-action]").forEach((b) => b.classList.remove("active"));
    const btn = document.querySelector(`.nav [data-action="show-${name}"]`);
    if (btn) btn.classList.add("active");
  }

  function wireNav() {
    const nav = document.querySelector(".nav");
    if (!nav) return;
    nav.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      const act = btn.getAttribute("data-action");
      if (!act?.startsWith("show-")) return;

      e.preventDefault();
      const view = act.replace("show-", "");
      showView(view);

      // Lazy load behaviors
      if (view === "overview") {
        loadOverview().catch(() => {});
      } else if (view === "reports") {
        // no auto fetch to avoid surprises
      } else if (view === "sops") {
        loadSops().catch(() => {});
      } else if (view === "summaries") {
        loadSummaries().catch(() => {});
      } else if (view === "search") {
        // no auto search; user triggers
      } else if (view === "activities") {
        loadActivities().catch(() => {});
      }
    });
  }

  // ===================== Reports =====================
  async function fetchReports() {
    const granularity = (el("rep-granularity")?.value || "daily").toLowerCase();
    const start = el("rep-start")?.value?.trim();
    const end = el("rep-end")?.value?.trim();
    const channel_id = el("rep-channel")?.value?.trim() || "";

    if (!start || !end) {
      alert("Please provide start and end dates (YYYY-MM-DD).");
      return;
    }

    const qs = new URLSearchParams({ granularity, start, end });
    if (channel_id) qs.set("channel_id", channel_id);

    try {
      const res = await fetch(`${API_BASE}/reports?${qs.toString()}`, {
        headers: authHeaders(),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || json.status === "error") {
        throw new Error(json.error || `Error ${res.status}`);
      }
      renderReports(json.items || []);
    } catch (err) {
      renderReports([]);
      console.warn(err);
    }
  }

  function renderReports(items) {
    const container = el("rep-results");
    if (!container) return;

    if (!items || !items.length) {
      container.innerHTML = "<p class='muted'>No reports found for the selected range.</p>";
      return;
    }

    const html = items
      .map((it) => {
        const counts = it.counts || { decisions: 0, todos: 0, facts: 0 };
        const label = it.label || "";
        const period = it.period || "";
        const ch = it.channel_filter || "";

        return `
          <div class="panel">
            <div class="grid">
              <div>
                <div class="badge">${escapeHtml(period)}</div>
                <div><strong>${escapeHtml(label)}</strong>${ch ? ` — Channel: ${escapeHtml(ch)}` : ""}</div>
              </div>
              <div><div class="muted">Decisions</div><div>${counts.decisions || 0}</div></div>
              <div><div class="muted">To-Dos</div><div>${counts.todos || 0}</div></div>
              <div><div class="muted">Facts</div><div>${counts.facts || 0}</div></div>
            </div>
            <pre style="white-space:pre-wrap;margin-top:8px">${escapeHtml(it.report_text || "")}</pre>
          </div>
        `;
      })
      .join("");

    container.innerHTML = html;
  }

  function wireReports() {
    el("rep-fetch-btn")?.addEventListener("click", fetchReports);
    if (el("rep-start") && !el("rep-start").value) el("rep-start").value = todayISO();
    if (el("rep-end") && !el("rep-end").value) el("rep-end").value = todayISO();
  }

  // ===================== SOP Library =====================
  async function loadSops() {
    const q = el("sop-q")?.value.trim() || "";
    const status = el("sop-status")?.value || "";

    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (status) qs.set("status", status);

    try {
      const res = await fetch(`${API_BASE}/sops?${qs.toString()}`, {
        headers: authHeaders(),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || json.status === "error") throw new Error(json.error || "Failed to load SOPs");
      renderSops(json.items || []);
    } catch (err) {
      console.warn(err);
      renderSops([]);
    }
  }

  function renderSops(items) {
    const tbody = el("sop-list");
    if (!tbody) return;

    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted">No SOPs yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = items
      .map((it) => {
        const created =
          it.created_at ? new Date(parseTsToMs(it.created_at)).toISOString().slice(0, 19).replace("T", " ") : "";
        return `
          <tr data-id="${escapeHtml(it.id)}">
            <td>${escapeHtml(it.topic || it.title || "")}</td>
            <td>${escapeHtml(it.tags || "")}</td>
            <td>${escapeHtml(it.status || "")}</td>
            <td>${escapeHtml(created)}</td>
            <td class="actions">
              <button class="ghost" data-action="view">View</button>
            </td>
          </tr>
        `;
      })
      .join("");

    tbody.querySelectorAll("button[data-action='view']").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const tr = e.target.closest("tr");
        const id = tr?.getAttribute("data-id");
        const row = items.find((x) => String(x.id) === String(id));
        alert(row?.sop_text || row?.content || "(empty)");
      });
    });
  }

  async function createSop() {
    const token = getToken();
    if (!token) {
      alert("Set your X-Auth-Token in Settings");
      return;
    }

    const topic = el("sop-topic")?.value.trim();
    if (!topic) {
      alert("Topic is required");
      return;
    }
    const channel_id = el("sop-channel")?.value.trim() || "";
    const tags = el("sop-tags")?.value.trim() || "";
    const generate = (el("sop-generate")?.value || "true") === "true";
    const days = parseInt(el("sop-days")?.value || "14", 10);

    const body = { topic, channel_id, tags, generate, days };
    if (!generate) {
      const sop_text = el("sop-text")?.value.trim();
      if (!sop_text) {
        alert("SOP text is required when not generating");
        return;
      }
      body.sop_text = sop_text;
    }

    try {
      const res = await fetch(`${API_BASE}/sops`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Auth-Token": token },
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || json.status === "error") throw new Error(json.error || res.status);
      el("sop-topic").value = "";
      el("sop-channel").value = "";
      el("sop-tags").value = "";
      if (!generate) el("sop-text").value = "";
      loadSops();
    } catch (err) {
      alert(`Create error: ${err.message}`);
    }
  }

  function wireSops() {
    el("sop-search-btn")?.addEventListener("click", loadSops);
    el("sop-save-btn")?.addEventListener("click", createSop);

    const genSel = el("sop-generate");
    const daysWrap = el("sop-days-wrap");
    const textWrap = el("sop-text-wrap");
    if (genSel && daysWrap && textWrap) {
      const update = () => {
        const gen = genSel.value === "true";
        daysWrap.style.display = gen ? "" : "none";
        textWrap.style.display = gen ? "none" : "";
      };
      genSel.addEventListener("change", update);
      update();
    }
  }

  // ===================== Summaries =====================
  async function loadSummaries() {
    const token = getToken();
    if (!token) return;

    const q = el("sum-q")?.value.trim() || "";
    const status = el("sum-status")?.value || "";
    const channel_id = el("sum-channel")?.value.trim() || "";
    const start = el("sum-start")?.value.trim() || "";
    const end = el("sum-end")?.value.trim() || "";

    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (status) qs.set("status", status);
    if (channel_id) qs.set("channel_id", channel_id);
    if (start) qs.set("start", start);
    if (end) qs.set("end", end);

    try {
      const res = await fetch(`${API_BASE}/summaries?${qs.toString()}`, {
        headers: authHeaders(),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || json.status === "error") throw new Error(json.error || "Failed to load summaries");
      renderSummaries(json.items || []);
    } catch (err) {
      console.warn(err);
      renderSummaries([]);
    }
  }

  function renderSummaries(items) {
    const tbody = el("sum-list");
    if (!tbody) return;

    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted">No summaries found.</td></tr>`;
      return;
    }

    tbody.innerHTML = items
      .map((it) => {
        const windowStr = it.period_start
          ? `${new Date(parseTsToMs(it.period_start)).toISOString().slice(0, 10)} → ${new Date(
              parseTsToMs(it.period_end || it.period_start)
            )
              .toISOString()
              .slice(0, 10)}`
          : it.date || "";
        const created =
          it.created_at ? new Date(parseTsToMs(it.created_at)).toISOString().slice(0, 19).replace("T", " ") : "";

        return `
          <tr data-id="${escapeHtml(it.id)}">
            <td>${escapeHtml(it.title || "")}</td>
            <td>${escapeHtml(it.channel_id || "")}</td>
            <td>${escapeHtml(windowStr)}</td>
            <td>${escapeHtml(it.status || "")}</td>
            <td>${escapeHtml(created)}</td>
            <td class="actions">
              <button class="ghost" data-action="view">View</button>
              <button class="ghost" data-action="copy">Copy</button>
            </td>
          </tr>
        `;
      })
      .join("");

    tbody.querySelectorAll("button[data-action]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const tr = e.target.closest("tr");
        const id = tr?.getAttribute("data-id");
        const row = items.find((x) => String(x.id) === String(id));
        if (!row) return;

        const action = e.target.getAttribute("data-action");
        if (action === "view") {
          alert(row.summary_text || "(empty)");
        } else if (action === "copy") {
          try {
            await navigator.clipboard.writeText(row.summary_text || "");
            alert("Summary copied to clipboard.");
          } catch {
            alert("Copy failed.");
          }
        }
      });
    });
  }

  async function createSummary() {
    const token = getToken();
    if (!token) {
      alert("Set your X-Auth-Token in Settings");
      return;
    }
    const title = el("sum-title")?.value.trim();
    if (!title) {
      alert("Title is required");
      return;
    }
    const channel_id = el("sum-create-channel")?.value.trim() || "";
    const tags = el("sum-tags")?.value.trim() || "";
    const generate = (el("sum-generate")?.value || "true") === "true";

    const body = { title, channel_id, tags, generate };
    if (generate) {
      const start = el("sum-start-create")?.value.trim();
      const end = el("sum-end-create")?.value.trim();
      if (!start || !end) {
        alert("Please provide window Start and End (YYYY-MM-DD).");
        return;
      }
      body.start = start;
      body.end = end;
    } else {
      const txt = el("sum-text")?.value.trim();
      if (!txt) {
        alert("Summary text is required when not generating");
        return;
      }
      body.summary_text = txt;
    }

    try {
      const res = await fetch(`${API_BASE}/summaries`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Auth-Token": token },
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || json.status === "error") throw new Error(json.error || res.status);
      el("sum-title").value = "";
      if (!generate) el("sum-text").value = "";
      loadSummaries();
    } catch (err) {
      alert(`Create error: ${err.message}`);
    }
  }

  function wireSummaries() {
    el("sum-search-btn")?.addEventListener("click", loadSummaries);
    el("sum-save-btn")?.addEventListener("click", createSummary);

    const genSel = el("sum-generate");
    const winWrap = el("sum-win-wrap");
    const textWrap = el("sum-text-wrap");
    if (genSel && winWrap && textWrap) {
      const update = () => {
        const gen = genSel.value === "true";
        winWrap.style.display = gen ? "" : "none";
        textWrap.style.display = gen ? "none" : "";
      };
      genSel.addEventListener("change", update);
      update();
    }

    if (el("sum-start") && !el("sum-start").value) el("sum-start").value = todayISO();
    if (el("sum-end") && !el("sum-end").value) el("sum-end").value = todayISO();
    if (el("sum-start-create") && !el("sum-start-create").value) el("sum-start-create").value = todayISO();
    if (el("sum-end-create") && !el("sum-end-create").value) el("sum-end-create").value = todayISO();
  }

  // ===================== Global Search =====================
  function gsSelectedTypes() {
    const t = [];
    if (el("gs-type-insights")?.checked) t.push("insights");
    if (el("gs-type-sops")?.checked) t.push("sops");
    if (el("gs-type-summaries")?.checked) t.push("summaries");
    return t.length ? t : ["insights", "sops", "summaries"];
  }

  function renderGlobalSearch(items) {
    const c = el("gs-results");
    if (!c) return;

    if (!items?.length) {
      c.innerHTML = `<p class="muted">No results. Try widening your query or date range.</p>`;
      return;
    }

    const html = items
      .map((it) => {
        const metaBits = [];
        if (it.channel_id) metaBits.push(`Channel: ${escapeHtml(it.channel_id)}`);
        if (it.tags) metaBits.push(`Tags: ${escapeHtml(it.tags)}`);
        if (it.status) metaBits.push(`Status: ${escapeHtml(it.status)}`);
        if (it.date) metaBits.push(`Date: ${escapeHtml(it.date)}`);

        const created = it.created_at
          ? new Date(parseTsToMs(it.created_at)).toISOString().slice(0, 19).replace("T", " ")
          : "";
        if (created) metaBits.push(`Created: ${created}`);

        const type = it.type || "";
        return `
          <div class="panel">
            <div class="grid">
              <div style="grid-column:1/-1">
                ${typeBadge(type)}
                <strong style="margin-left:6px">${escapeHtml(it.title || "(untitled)")}</strong>
              </div>
              <div style="grid-column:1/-1" class="muted">${metaBits.join(" • ")}</div>
            </div>
            <pre style="white-space:pre-wrap;margin-top:8px">${escapeHtml(it.text || "")}</pre>
            <div class="actions" style="margin-top:8px">
              <button class="ghost" data-gs-copy="${escapeHtml(it.id || "")}">Copy</button>
            </div>
          </div>
        `;
      })
      .join("");

    c.innerHTML = html;

    c.querySelectorAll("button[data-gs-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const pre = btn.closest(".panel")?.querySelector("pre");
        try {
          await navigator.clipboard.writeText(pre?.textContent || "");
          alert("Copied to clipboard.");
        } catch {
          alert("Copy failed.");
        }
      });
    });
  }

  async function performGlobalSearch() {
    const q = el("gs-q")?.value.trim() || "";
    const channel_id = el("gs-channel")?.value.trim() || "";
    const status = el("gs-status")?.value || "";
    const start = el("gs-start")?.value.trim() || "";
    const end = el("gs-end")?.value.trim() || "";

    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (channel_id) qs.set("channel_id", channel_id);
    if (status) qs.set("status", status);
    if (start) qs.set("start", start);
    if (end) qs.set("end", end);

    const headers = authHeaders();
    const selected = gsSelectedTypes();

    const tasks = [];
    if (selected.includes("insights")) {
      const iq = new URLSearchParams(qs);
      tasks.push(
        fetch(`${API_BASE}/search?${iq.toString()}`, { headers })
          .then((r) => r.json().catch(() => ({ items: [] })))
          .then((j) => ({ kind: "insights", items: j.items || [] }))
          .catch(() => ({ kind: "insights", items: [] }))
      );
    }
    if (selected.includes("summaries")) {
      tasks.push(
        fetch(`${API_BASE}/summaries?${qs.toString()}`, { headers })
          .then((r) => r.json().catch(() => ({ items: [] })))
          .then((j) => ({ kind: "summaries", items: j.items || [] }))
          .catch(() => ({ kind: "summaries", items: [] }))
      );
    }
    if (selected.includes("sops")) {
      tasks.push(
        fetch(`${API_BASE}/sops?${qs.toString()}`, { headers })
          .then((r) => r.json().catch(() => ({ items: [] })))
          .then((j) => ({ kind: "sops", items: j.items || [] }))
          .catch(() => ({ kind: "sops", items: [] }))
      );
    }

    const results = await Promise.all(tasks);

    let items = [];
    for (const r of results) {
      if (r.kind === "insights") {
        items = items.concat(
          r.items.map((x) => ({
            id: x.id ?? x._id ?? `ins-${Math.random().toString(36).slice(2)}`,
            type: "insight",
            title: x.title || x.label || "Insight",
            text: x.text || x.report_text || "",
            channel_id: x.channel_id || x.channel || "",
            tags: x.tags || "",
            status: x.status || "",
            date: x.date || x.day || "",
            created_at: x.created_at || null,
          }))
        );
      } else if (r.kind === "summaries") {
        items = items.concat(
          r.items.map((x) => ({
            id: x.id,
            type: "summary",
            title: x.title || `Summary ${x.id}`,
            text: x.summary_text || "",
            channel_id: x.channel_id || "",
            tags: x.tags || "",
            status: x.status || "",
            date:
              x.period_start && x.period_end
                ? `${new Date(parseTsToMs(x.period_start)).toISOString().slice(0, 10)} → ${new Date(
                    parseTsToMs(x.period_end)
                  )
                    .toISOString()
                    .slice(0, 10)}`
                : x.date || "",
            created_at: x.created_at || null,
          }))
        );
      } else if (r.kind === "sops") {
        items = items.concat(
          r.items.map((x) => ({
            id: x.id,
            type: "sop",
            title: x.topic || x.title || "SOP",
            text: x.sop_text || x.content || "",
            channel_id: x.channel_id || "",
            tags: x.tags || "",
            status: x.status || "",
            date: x.date || "",
            created_at: x.created_at || null,
          }))
        );
      }
    }

    renderGlobalSearch(items);
  }

  function wireGlobalSearch() {
    el("gs-search-btn")?.addEventListener("click", performGlobalSearch);
    if (el("gs-start") && !el("gs-start").value) el("gs-start").value = todayISO();
    if (el("gs-end") && !el("gs-end").value) el("gs-end").value = todayISO();
  }

  // ===================== Activities =====================
  async function loadActivities() {
    const start = el("activities-start")?.value?.trim() || "";
    const end = el("activities-end")?.value?.trim() || "";
    const channel_id = el("activities-channel")?.value?.trim() || "";
    const status = el("activities-status")?.value || "";

    const qs = new URLSearchParams();
    if (start) qs.set("start", start);
    if (end) qs.set("end", end);
    if (channel_id) qs.set("channel_id", channel_id);
    if (status) qs.set("status", status);

    try {
      const res = await fetch(`${API_BASE}/activities?${qs.toString()}`, {
        headers: authHeaders(),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok || json.status === "error") throw new Error(json.error || "Failed to load activities");
      renderActivities(json.items || []);
    } catch (err) {
      console.warn(err);
      renderActivities([]);
    }
  }

  function renderActivities(items) {
    const list = el("activities-list") || el("activities-results");
    if (!list) return;

    if (!items?.length) {
      list.innerHTML = `<div class="muted">No recent activities for the selected filters.</div>`;
      return;
    }

    const html = items
      .map((it) => {
        const kind = it.type || it.kind || "event";
        const ts = parseTsToMs(it.timestamp || it.ts || it.created_at);
        const when = ts ? new Date(ts).toISOString().replace("T", " ").slice(0, 19) : "";
        const channel = it.channel_id || it.channel || "";
        const text =
          it.description ||
          it.text ||
          (it.meta && (it.meta.message_preview || it.meta.text)) ||
          it.title ||
          "";

        const counts = (it.meta && it.meta.counts) || null;
        const countsHtml = counts
          ? `
            <div class="grid" style="margin-top:8px">
              <div><div class="muted">Decisions</div><div>${counts.decisions || 0}</div></div>
              <div><div class="muted">To-Dos</div><div>${counts.todos || 0}</div></div>
              <div><div class="muted">Facts</div><div>${counts.facts || 0}</div></div>
            </div>
          `
          : "";

        const metaLine = [when ? `When: ${escapeHtml(when)}` : "", channel ? `Channel: ${escapeHtml(channel)}` : ""]
          .filter(Boolean)
          .join(" • ");

        return `
          <div class="panel">
            <div class="grid">
              <div style="grid-column:1/-1">
                ${typeBadge(kind)}
                <strong style="margin-left:6px">${escapeHtml(it.title || kind.toUpperCase())}</strong>
              </div>
              <div style="grid-column:1/-1" class="muted">${metaLine}</div>
            </div>
            <pre style="white-space:pre-wrap;margin-top:8px">${escapeHtml(text)}</pre>
            ${countsHtml}
            <div class="actions" style="margin-top:8px">
              <button class="ghost" data-act-copy="${escapeHtml(it.id || "")}">Copy</button>
              <button class="ghost" data-act-raw="${escapeHtml(it.id || "")}">View raw</button>
            </div>
          </div>
        `;
      })
      .join("");

    list.innerHTML = html;

    list.querySelectorAll("button[data-act-copy]").forEach((b) => {
      b.addEventListener("click", async (e) => {
        const panel = e.target.closest(".panel");
        const pre = panel?.querySelector("pre");
        try {
          await navigator.clipboard.writeText(pre?.textContent || "");
          alert("Copied to clipboard.");
        } catch {
          alert("Copy failed.");
        }
      });
    });

    list.querySelectorAll("button[data-act-raw]").forEach((b) => {
      b.addEventListener("click", () => {
        const card = b.closest(".panel");
        const raw = card?.textContent || "";
        alert(raw.slice(0, 4000));
      });
    });
  }

  function wireActivities() {
    el("activities-fetch-btn")?.addEventListener("click", loadActivities);
    if (el("activities-start") && !el("activities-start").value) el("activities-start").value = todayISO();
    if (el("activities-end") && !el("activities-end").value) el("activities-end").value = todayISO();
  }

  // ===================== Overview =====================
  async function loadOverview() {
    const setCount = (id, val) => {
      const n = el(id);
      if (n) n.textContent = String(val ?? 0);
    };

    const headers = authHeaders();
    const today = todayISO();
    const wStart = weekStartISO();
    const [todayStartMs, todayEndMs] = dayBoundsMs(today);
    const [weekStartMs, weekEndMs] = rangeBoundsMs(wStart, today);

    try {
      // Reports: call daily for today and week
      const reportsTodayP = fetch(`${API_BASE}/reports?granularity=daily&start=${today}&end=${today}`, { headers })
        .then((r) => r.json().catch(() => ({})))
        .then((j) => (Array.isArray(j.items) ? j.items.length : 0))
        .catch(() => 0);
      const reportsWeekP = fetch(`${API_BASE}/reports?granularity=daily&start=${wStart}&end=${today}`, { headers })
        .then((r) => r.json().catch(() => ({})))
        .then((j) => (Array.isArray(j.items) ? j.items.length : 0))
        .catch(() => 0);

      // Summaries: fetch week; compute week + today counts
      const summariesWeekP = fetch(`${API_BASE}/summaries?start=${wStart}&end=${today}`, { headers })
        .then((r) => r.json().catch(() => ({ items: [] })))
        .catch(() => ({ items: [] }));

      // Activities: fetch week; compute week + today counts
      const activitiesWeekP = fetch(`${API_BASE}/activities?start=${wStart}&end=${today}`, { headers })
        .then((r) => r.json().catch(() => ({ items: [] })))
        .catch(() => ({ items: [] }));

      // SOPs: fetch all or server-filtered; compute week + today counts locally
      const sopsP = fetch(`${API_BASE}/sops?start=${wStart}&end=${today}`, { headers })
        .then((r) => r.json().catch(() => ({ items: [] })))
        .catch(() => ({ items: [] }));

      const [repToday, repWeek, summariesRes, activitiesRes, sopsRes] = await Promise.all([
        reportsTodayP,
        reportsWeekP,
        summariesWeekP,
        activitiesWeekP,
        sopsP,
      ]);

      // Reports
      setCount("ovr-reports-today", repToday);
      setCount("ovr-reports-week", repWeek);

      // Summaries
      const sumItems = Array.isArray(summariesRes.items) ? summariesRes.items : [];
      const sumWeek = sumItems.length;
      const sumToday = sumItems.filter((x) => inMsRange(parseTsToMs(x.created_at), todayStartMs, todayEndMs)).length;
      setCount("ovr-summaries-today", sumToday);
      setCount("ovr-summaries-week", sumWeek);

      // Activities
      const actItems = Array.isArray(activitiesRes.items) ? activitiesRes.items : [];
      const actWeek = actItems.length;
      const actToday = actItems.filter((x) => inMsRange(parseTsToMs(x.timestamp || x.ts || x.created_at), todayStartMs, todayEndMs)).length;
      setCount("ovr-activities-today", actToday);
      setCount("ovr-activities-week", actWeek);

      // SOPs (filter client-side by created_at)
      const sopItems = Array.isArray(sopsRes.items) ? sopsRes.items : [];
      const sopWeek = sopItems.filter((x) => inMsRange(parseTsToMs(x.created_at), weekStartMs, weekEndMs)).length;
      const sopToday = sopItems.filter((x) => inMsRange(parseTsToMs(x.created_at), todayStartMs, todayEndMs)).length;
      setCount("ovr-sops-today", sopToday);
      setCount("ovr-sops-week", sopWeek);
    } catch (err) {
      console.warn("Overview load error:", err);
      ["ovr-reports-today","ovr-reports-week","ovr-sops-today","ovr-sops-week","ovr-summaries-today","ovr-summaries-week","ovr-activities-today","ovr-activities-week"].forEach((id) => setCount(id, 0));
    }
  }

  function wireOverview() {
    el("ovr-refresh-btn")?.addEventListener("click", () => loadOverview());
  }

  // ===================== Init =====================
  document.addEventListener("DOMContentLoaded", () => {
    wireNav();
    wireSettings();
    wireReports();
    wireSops();
    wireSummaries();
    wireGlobalSearch();
    wireActivities();
    wireOverview();

    // Start on Overview and populate it
    showView("overview");
    loadOverview().catch(() => {});
  });
})();