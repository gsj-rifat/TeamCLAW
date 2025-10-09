(function () {
  // ===================== Config =====================
  const API_BASE = "/dashboard/api"; // change if your backend path differs

  // ===================== Utilities =====================
  const el = (id) => document.getElementById(id);
  const todayISO = () => new Date().toISOString().slice(0, 10);

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[m]));
  }

  // ===================== Token (Settings) =====================
  function getToken() {
    return localStorage.getItem("dash_token") || "";
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

      // optional: lazy load per view
      if (view === "sops") loadSops().catch(() => {});
      if (view === "summaries") loadSummaries().catch(() => {});
    });
  }

  // ===================== Reports =====================
  async function fetchReports() {
    const token = getToken();
    if (!token) {
      alert("Please set your X-Auth-Token in Settings first.");
      return;
    }
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
        headers: { "X-Auth-Token": token },
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
    const token = getToken();
    if (!token) {
      return; // quietly ignore if no token
    }
    const q = el("sop-q")?.value.trim() || "";
    const status = el("sop-status")?.value || "";

    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (status) qs.set("status", status);

    try {
      const res = await fetch(`${API_BASE}/sops?${qs.toString()}`, {
        headers: { "X-Auth-Token": token },
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
          it.created_at ? new Date(it.created_at * 1000).toISOString().slice(0, 19).replace("T", " ") : "";
        return `
          <tr data-id="${escapeHtml(it.id)}">
            <td>${escapeHtml(it.topic)}</td>
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
        alert(row?.sop_text || "(empty)");
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
      // reset
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
        headers: { "X-Auth-Token": getToken() },
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
          ? `${new Date(it.period_start * 1000).toISOString().slice(0, 10)} → ${new Date(
              (it.period_end || it.period_start) * 1000
            )
              .toISOString()
              .slice(0, 10)}`
          : it.date || "";
        const created =
          it.created_at ? new Date(it.created_at * 1000).toISOString().slice(0, 19).replace("T", " ") : "";

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

    // Toggle create controls
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

    // Defaults
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
          ? new Date(it.created_at * 1000).toISOString().slice(0, 19).replace("T", " ")
          : "";
        if (created) metaBits.push(`Created: ${created}`);

        const type = it.type || "";
        const badge = `<span class="badge">${type.toUpperCase()}</span>`;

        return `
          <div class="panel">
            <div class="grid">
              <div style="grid-column:1/-1">
                ${badge}
                <strong style="margin-left:6px">${escapeHtml(it.title || "(untitled)")}</strong>
              </div>
              <div style="grid-column:1/-1" class="muted">${metaBits.join(" • ")}</div>
            </div>
            <pre style="white-space:pre-wrap;margin-top:8px">${escapeHtml(it.text || "")}</pre>
            <div class="actions" style="margin-top:8px">
              <button class="ghost" data-gs-copy="${escapeHtml(it.id)}">Copy</button>
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
    const token = getToken();
    if (!token) {
      alert("Please set your X-Auth-Token in Settings first.");
      return;
    }

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

    // This version fetches each type separately to keep compatibility with typical backends
    const headers = { "X-Auth-Token": token };
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
                ? `${new Date(x.period_start * 1000).toISOString().slice(0, 10)} → ${new Date(
                    x.period_end * 1000
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

  // ===================== Init =====================
  document.addEventListener("DOMContentLoaded", () => {
    wireNav();
    wireSettings();
    wireReports();
    wireSops();
    wireSummaries();
    wireGlobalSearch();

    // start on Overview
    showView("overview");
  });
})();