(function () {
  const API_BASE = "/dashboard/api";

  function getToken() {
    return localStorage.getItem("dash_token") || "";
  }

  function setToken(val) {
    localStorage.setItem("dash_token", val || "");
  }

  function showView(viewName) {
  // Each major section should have data-view="<name>"
  document.querySelectorAll('[data-view]').forEach(el => el.classList.add('hidden'));
  const active = document.querySelector(`[data-view="${viewName}"]`);
  if (active) active.classList.remove('hidden');

  // Optional: update active state on nav
  document.querySelectorAll('[data-action^="show-"]').forEach(a => a.classList.remove('active'));
  const nav = document.querySelector(`[data-action="show-${viewName}"]`);
  if (nav) nav.classList.add('active');
}

  function el(id) { return document.getElementById(id); }

  // Settings handlers
  const tokenInput = el("token-input");
  const tokenSaveBtn = el("token-save-btn");
  const tokenStatus = el("token-status");
  const todayISO = () => new Date().toISOString().slice(0, 10);

  if (tokenInput && tokenSaveBtn) {
    tokenInput.value = getToken();
    tokenSaveBtn.addEventListener("click", () => {
      setToken(tokenInput.value.trim());
      tokenStatus.textContent = "Token saved for this browser.";
      setTimeout(() => tokenStatus.textContent = "", 2500);
    });
  }

  // Render helper
  function renderReports(items) {
    const container = el("rep-results");
    if (!container) return;

    if (!items || !items.length) {
      container.innerHTML = "<p class='muted'>No reports found for the selected range.</p>";
      return;
    }

    const html = items.map((it, idx) => {
      const counts = it.counts || { decisions: 0, todos: 0, facts: 0 };
      const label = it.label || "";
      const period = it.period || "";
      const ch = it.channel_filter || "";
      return `
        <div class="panel" data-idx="${idx}">
          <div class="grid">
            <div>
              <div class="badge">${period}</div>
              <div><strong>${label}</strong>${ch ? ` — Channel: ${ch}` : ""}</div>
            </div>
            <div><div class="muted">Decisions</div><div>${counts.decisions || 0}</div></div>
            <div><div class="muted">To-Dos</div><div>${counts.todos || 0}</div></div>
            <div><div class="muted">Facts</div><div>${counts.facts || 0}</div></div>
          </div>
          <pre style="white-space:pre-wrap;margin-top:8px">${(it.report_text || "").replace(/</g,"&lt;")}</pre>
          <div class="actions" style="margin-top:8px">
            <button class="ghost" data-download="1" data-period="${period}" data-label="${label}" data-channel="${ch}">
              Download CSV
            </button>
          </div>
        </div>
      `;
    }).join("");

    container.innerHTML = html;

    // Attach download handlers
    container.querySelectorAll("button[data-download='1']").forEach(btn => {
      btn.addEventListener("click", async (ev) => {
        ev.preventDefault();
        const period = btn.getAttribute("data-period") || "daily";
        const label = btn.getAttribute("data-label") || "";
        const ch = btn.getAttribute("data-channel") || "";
        await downloadCsv(period, label, ch);
      });
    });
  }

  async function fetchReports() {
    const token = getToken();
    if (!token) {
      alert("Please set your X-Auth-Token in Settings first.");
      return;
    }

    const granularity = (el("rep-granularity")?.value || "daily").toLowerCase();
    const start = el("rep-start")?.value.trim();
    const end = el("rep-end")?.value.trim();
    const channel_id = el("rep-channel")?.value.trim();

    if (!start || !end) {
      alert("Please provide start and end dates (YYYY-MM-DD).");
      return;
    }

    const qs = new URLSearchParams({ granularity, start, end });
    if (channel_id) qs.set("channel_id", channel_id);

    const res = await fetch(`${API_BASE}/reports?${qs.toString()}`, {
      headers: { "X-Auth-Token": token }
    });
    const json = await res.json();
    if (!res.ok || json.status === "error") {
      alert(`Error: ${json.error || res.status}`);
      return;
    }
    renderReports(json.items || []);
  }

  async function downloadCsv(granularity, dateLabel, channel_id) {
    const token = getToken();
    if (!token) {
      alert("Please set your X-Auth-Token in Settings first.");
      return;
    }
    const qs = new URLSearchParams({ granularity, date: dateLabel });
    if (channel_id) qs.set("channel_id", channel_id);

    const res = await fetch(`${API_BASE}/reports/export.csv?${qs.toString()}`, {
      headers: { "X-Auth-Token": token }
    });
    if (!res.ok) {
      const t = await res.text();
      alert(`CSV error: ${t}`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `report_${granularity}_${dateLabel}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // Wire up Fetch button
  const fetchBtn = el("rep-fetch-btn");
  if (fetchBtn) {
    fetchBtn.addEventListener("click", fetchReports);
  }

  // Default report date inputs
if (el("repstart") && !el("repstart").value) el("repstart").value = todayISO();
if (el("repend") && !el("repend").value) el("repend").value = todayISO();

  console.log("Dashboard Reports wired (Step 3).");

  // ----- SOP Library -----
  const sopGenSel = el("sop-generate");
  const sopDaysWrap = el("sop-days-wrap");
  const sopTextWrap = el("sop-text-wrap");
  if (sopGenSel) {
    sopGenSel.addEventListener("change", () => {
      const gen = sopGenSel.value === "true";
      sopDaysWrap.style.display = gen ? "" : "none";
      sopTextWrap.style.display = gen ? "none" : "";
    });
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

  async function loadSops() {
    const token = getToken();
    if (!token) return;
    const q = el("sop-q")?.value.trim() || "";
    const status = el("sop-status")?.value || "";
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (status) qs.set("status", status);

    const res = await fetch(`${API_BASE}/sops?${qs.toString()}`, {
      headers: { "X-Auth-Token": token }
    });
    const json = await res.json();
    if (!res.ok || json.status === "error") {
      alert(json.error || "Failed to load SOPs");
      return;
    }
    renderSops(json.items || []);
  }

  function renderSops(items) {
    const tbody = el("sop-list");
    if (!tbody) return;
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted">No SOPs yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(it => {
      const canEdit = hasRole("user");   // user or admin
      const canDelete = hasRole("admin");
      const actions = [
        `<button class="ghost" data-action="view">View</button>`,
        ...(canEdit ? [`<button class="ghost" data-action="edit" data-requires-role="user">Edit</button>`] : []),
        ...(canDelete ? [`<button class="ghost" data-action="delete" data-requires-role="admin">Delete</button>`] : []),
      ].join(" ");
      return `
        <tr data-id="${it.id}">
          <td>${escapeHtml(it.topic)}</td>
          <td>${escapeHtml(it.tags || "")}</td>
          <td>${escapeHtml(it.status || "")}</td>
          <td>${new Date((it.created_at||0)*1000).toISOString().slice(0,19).replace('T',' ')}</td>
          <td class="actions">${actions}</td>
        </tr>
      `;
    }).join("");

    // Wire button handlers (unchanged)
    tbody.querySelectorAll("button[data-action]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const tr = e.target.closest("tr");
        const id = tr?.getAttribute("data-id");
        const action = e.target.getAttribute("data-action");
        const row = items.find(x => String(x.id) === String(id));
        if (!id || !row) return;

        if (action === "view") {
          alert(row.sop_text || "(empty)");
        } else if (action === "edit") {
          if (!hasRole("user")) { alert("Not authorized."); return; }
          const newTopic = prompt("Edit topic", row.topic);
          if (newTopic === null) return;
          const newTags = prompt("Edit tags (comma-separated)", row.tags || "");
          if (newTags === null) return;
          const newStatus = prompt("Edit status (draft|active|deprecated)", row.status || "active");
          if (newStatus === null) return;
          const changeText = confirm("Edit SOP text as well?");
          let patch = { topic: newTopic.trim(), tags: newTags.trim(), status: newStatus.trim() };
          if (changeText) {
            const newText = prompt("Paste new SOP text", row.sop_text || "");
            if (newText === null) return;
            patch.sop_text = newText;
          }
          await updateSop(id, patch);
          await loadSops();
        } else if (action === "delete") {
          if (!hasRole("admin")) { alert("Not authorized."); return; }
          if (confirm("Delete this SOP? This cannot be undone.")) {
            await deleteSop(id);
            await loadSops();
          }
        }
      });
    });

    // After render, re-enforce data-requires-role visibility
    enforceRoleVisibility();
  }

  async function createSop() {
    const token = getToken();
    if (!token) { alert("Set your X-Auth-Token in Settings"); return; }

    const topic = el("sop-topic")?.value.trim();
    if (!topic) { alert("Topic is required"); return; }
    const channel_id = el("sop-channel")?.value.trim();
    const tags = el("sop-tags")?.value.trim();
    const generate = (el("sop-generate")?.value || "true") === "true";
    const days = parseInt(el("sop-days")?.value || "14", 10);

    const body = { topic, channel_id, tags, generate, days };
    if (!generate) {
      const sop_text = el("sop-text")?.value.trim();
      if (!sop_text) { alert("SOP text is required when not generating"); return; }
      body.sop_text = sop_text;
    }

    const res = await fetch(`${API_BASE}/sops`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Auth-Token": token },
      body: JSON.stringify(body)
    });
    const json = await res.json();
    if (!res.ok || json.status === "error") {
      alert(`Create error: ${json.error || res.status}`);
      return;
    }

    // Reset form and reload list
    el("sop-topic").value = "";
    el("sop-channel").value = "";
    el("sop-tags").value = "";
    if (!generate) el("sop-text").value = "";
    loadSops();
  }

  async function updateSop(id, patch) {
    const token = getToken();
    const res = await fetch(`${API_BASE}/sops/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Auth-Token": token },
      body: JSON.stringify(patch || {})
    });
    if (!res.ok) {
      const t = await res.text();
      alert(`Update failed: ${t}`);
    }
  }

  async function deleteSop(id) {
    const token = getToken();
    const res = await fetch(`${API_BASE}/sops/${id}`, {
      method: "DELETE",
      headers: { "X-Auth-Token": token }
    });
    if (!res.ok) {
      const t = await res.text();
      alert(`Delete failed: ${t}`);
    }
  }

  // Bind events
  if (el("sop-search-btn")) el("sop-search-btn").addEventListener("click", loadSops);
  if (el("sop-save-btn")) el("sop-save-btn").addEventListener("click", createSop);

  // Initial load
  // Initialize: detect role, then load panels
  (async () => {
    await detectRole();
    // Re-run visibility in case token was added after page load
    enforceRoleVisibility();
    // Now load data
    try { await loadSops(); } catch {}
    try { await loadSummaries(); } catch {}
    // Optional: you can auto-run a search here if desired
    // try { await performGlobalSearch(); } catch {}
  })();
  // ----- Summaries Archive -----
  const sumGenSel = el("sum-generate");
  const sumWinWrap = el("sum-win-wrap");
  const sumTextWrap = el("sum-text-wrap");
  if (sumGenSel) {
    sumGenSel.addEventListener("change", () => {
      const gen = sumGenSel.value === "true";
      sumWinWrap.style.display = gen ? "" : "none";
      sumTextWrap.style.display = gen ? "none" : "";
    });
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

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

    const res = await fetch(`${API_BASE}/summaries?${qs.toString()}`, {
      headers: { "X-Auth-Token": token }
    });
    const json = await res.json();
    if (!res.ok || json.status === "error") {
      alert(json.error || "Failed to load summaries");
      return;
    }
    renderSummaries(json.items || []);
  }

  function renderSummaries(items) {
    const tbody = el("sum-list");
    if (!tbody) return;
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted">No summaries found.</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(it => {
      const windowStr = it.period_start
        ? `${new Date(it.period_start*1000).toISOString().slice(0,10)} → ${new Date((it.period_end||it.period_start)*1000).toISOString().slice(0,10)}`
        : (it.date || "");
      return `
        <tr data-id="${it.id}">
          <td>${escapeHtml(it.title || "")}</td>
          <td>${escapeHtml(it.channel_id || "")}</td>
          <td>${escapeHtml(windowStr)}</td>
          <td>${escapeHtml(it.status || "")}</td>
          <td>${new Date((it.created_at||0)*1000).toISOString().slice(0,19).replace('T',' ')}</td>
          <td class="actions">
            <button class="ghost" data-action="view">View</button>
            <button class="ghost" data-action="copy">Copy</button>
          </td>
        </tr>
      `;
    }).join("");

    tbody.querySelectorAll("button[data-action]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const tr = e.target.closest("tr");
        const id = tr?.getAttribute("data-id");
        const row = items.find(x => String(x.id) === String(id));
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
    if (!token) { alert("Set your X-Auth-Token in Settings"); return; }

    const title = el("sum-title")?.value.trim();
    if (!title) { alert("Title is required"); return; }

    const channel_id = el("sum-create-channel")?.value.trim() || "";
    const tags = el("sum-tags")?.value.trim() || "";
    const generate = (el("sum-generate")?.value || "true") === "true";

    const body = { title, channel_id, tags, generate };

    if (generate) {
      const start = el("sum-start-create")?.value.trim();
      const end = el("sum-end-create")?.value.trim();
      if (!start || !end) { alert("Please provide window Start and End (YYYY-MM-DD)."); return; }
      body.start = start; body.end = end;
    } else {
      const txt = el("sum-text")?.value.trim();
      if (!txt) { alert("Summary text is required when not generating"); return; }
      body.summary_text = txt;
    }

    const res = await fetch(`${API_BASE}/summaries`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Auth-Token": token },
      body: JSON.stringify(body)
    });
    const json = await res.json();
    if (!res.ok || json.status === "error") {
      alert(`Create error: ${json.error || res.status}`);
      return;
    }

    // Reset minimal fields and reload
    el("sum-title").value = "";
    if (!generate) el("sum-text").value = "";
    loadSummaries();
  }

  // Wire buttons
  if (el("sum-search-btn")) el("sum-search-btn").addEventListener("click", loadSummaries);
  if (el("sum-save-btn")) el("sum-save-btn").addEventListener("click", createSummary);

  // Defaults for convenience (summaries)

if (el("sumstart") && !el("sumstart").value) el("sumstart").value = todayISO();
if (el("sumend") && !el("sumend").value) el("sumend").value = todayISO();
if (el("sum-start-create") && !el("sum-start-create").value) el("sum-start-create").value = todayISO();
if (el("sum-end-create") && !el("sum-end-create").value) el("sum-end-create").value = todayISO();

  // Initial load
  // Initialize: detect role, then load panels
  (async () => {
    await detectRole();
    // Re-run visibility in case token was added after page load
    enforceRoleVisibility();
    // Now load data
    try { await loadSops(); } catch {}
    try { await loadSummaries(); } catch {}
    // Optional: you can auto-run a search here if desired
    // try { await performGlobalSearch(); } catch {}
  })();

  // ----- Global Search -----
  function gsSelectedTypes() {
    const t = [];
    if (el("gs-type-insights")?.checked) t.push("insights");
    if (el("gs-type-sops")?.checked) t.push("sops");
    if (el("gs-type-summaries")?.checked) t.push("summaries");
    return t.length ? t : ["insights","sops","summaries"];
  }

  if (typeof escapeHtml !== "function") {
    window.escapeHtml = function (s) {
      return String(s || "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    };
  }

  function typeBadge(t) {
    const m = { insight: "badge", sop: "badge", summary: "badge" };
    const label = t === "insight" ? "INSIGHT" : t === "sop" ? "SOP" : "SUMMARY";
    return `<span class="${m[t] || 'badge'}">${label}</span>`;
  }

  function renderGlobalSearch(items) {
    const c = el("gs-results");
    if (!c) return;
    if (!items || !items.length) {
      c.innerHTML = `<p class="muted">No results. Try widening your query or date range.</p>`;
      return;
    }
    const html = items.map(it => {
      const metaBits = [];
      if (it.channel_id) metaBits.push(`Channel: ${escapeHtml(it.channel_id)}`);
      if (it.tags) metaBits.push(`Tags: ${escapeHtml(it.tags)}`);
      if (it.status) metaBits.push(`Status: ${escapeHtml(it.status)}`);
      if (it.date) metaBits.push(`Date: ${escapeHtml(it.date)}`);
      const created = it.created_at ? new Date(it.created_at*1000).toISOString().slice(0,19).replace('T',' ') : "";
      if (created) metaBits.push(`Created: ${created}`);

      return `
        <div class="panel">
          <div class="grid">
            <div style="grid-column:1/-1">
              ${typeBadge(it.type || '')}
              <strong style="margin-left:6px">${escapeHtml(it.title || "(untitled)")}</strong>
            </div>
            <div style="grid-column:1/-1" class="muted">${metaBits.join(" • ")}</div>
          </div>
          <pre style="white-space:pre-wrap;margin-top:8px">${escapeHtml(it.text || "")}</pre>
          <div class="actions" style="margin-top:8px">
            <button class="ghost" data-gs-copy="${it.id}" data-gs-type="${it.type}">Copy</button>
          </div>
        </div>
      `;
    }).join("");
    c.innerHTML = html;

    // Copy handlers
    c.querySelectorAll("button[data-gs-copy]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const idx = [...c.querySelectorAll("button[data-gs-copy]")].indexOf(btn);
        const panels = c.querySelectorAll(".panel pre");
        const pre = panels[idx];
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
  if (!token) { alert("Please set your X-Auth-Token in Settings first."); return; }

  // Read filters from your existing inputs
  const q = el("gs-q")?.value.trim() || "";
  const channel_id = el("gs-channel")?.value.trim() || "";
  const status = el("gs-status")?.value || "";
  const start = el("gs-start")?.value.trim() || "";
  const end = el("gs-end")?.value.trim() || "";

  // Build common query string
  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  if (channel_id) qs.set("channel_id", channel_id);
  if (status) qs.set("status", status);
  if (start) qs.set("start", start);
  if (end) qs.set("end", end);

  // Endpoints: insights via /search, plus direct summaries + sops
  // Note: we ask /search only for insights; summaries and sops come from their dedicated endpoints
  const insightsUrl = `${API_BASE}/search?${new URLSearchParams({ ...Object.fromEntries(qs), types: "insights" }).toString()}`;
  const summariesUrl = `${API_BASE}/summaries?${qs.toString()}`;
  const sopsUrl = `${API_BASE}/sops?${qs.toString()}`;

  try {
    const headers = { "X-Auth-Token": token };
    const [insRes, sumRes, sopRes] = await Promise.all([
      fetch(insightsUrl, { headers }),
      fetch(summariesUrl, { headers }),
      fetch(sopsUrl, { headers }),
    ]);

    const [insJson, sumJson, sopJson] = await Promise.all([
      insRes.json().catch(() => ({ items: [] })),
      sumRes.json().catch(() => ({ items: [] })),
      sopRes.json().catch(() => ({ items: [] })),
    ]);

    if (!insRes.ok && insJson?.error) { console.warn("Insights search error:", insJson.error); }
    if (!sumRes.ok && sumJson?.error) { console.warn("Summaries search error:", sumJson.error); }
    if (!sopRes.ok && sopJson?.error) { console.warn("SOPs search error:", sopJson.error); }

    // Normalize into the shape your renderGlobalSearch expects
    const insights = (insJson.items || []).map(x => ({
      id: x.id ?? x._id ?? `ins-${Math.random().toString(36).slice(2)}`,
      type: "insight",
      title: x.title || x.label || "Insight",
      text: x.text || x.report_text || "",
      channel_id: x.channel_id || x.channel || "",
      tags: x.tags || "",
      status: x.status || "",
      date: x.date || x.day || "",
      created_at: x.created_at || x.ts || null,
    }));

    const summaries = (sumJson.items || []).map(x => ({
      id: x.id,
      type: "summary",
      title: x.title || `Summary ${x.id}`,
      text: x.summary_text || "",
      channel_id: x.channel_id || "",
      tags: x.tags || "",
      status: x.status || "",
      date: x.period_start && x.period_end
        ? `${new Date(x.period_start * 1000).toISOString().slice(0,10)} → ${new Date(x.period_end * 1000).toISOString().slice(0,10)}`
        : (x.date || ""),
      created_at: x.created_at || null,
    }));

    const sops = (sopJson.items || []).map(x => ({
      id: x.id,
      type: "sop",
      title: x.topic || x.title || "SOP",
      text: x.sop_text || x.content || "",
      channel_id: x.channel_id || "",
      tags: x.tags || "",
      status: x.status || "",
      date: x.date || "",
      created_at: x.created_at || null,
    }));

    // Optional: filter by selected types if you use checkboxes (insights/summaries/sops)
    let items = [...insights, ...summaries, ...sops];
    if (typeof gsSelectedTypes === "function") {
      const chosen = new Set(gsSelectedTypes().map(t => t.replace(/s$/, ""))); // "insights" -> "insight"
      items = items.filter(it => chosen.has(it.type));
    }

    renderGlobalSearch(items);
  } catch (err) {
    console.error("[search] error", err);
    alert("Search error. Check console for details.");
  }
}

  if (el("gs-search-btn")) {
    el("gs-search-btn").addEventListener("click", performGlobalSearch);
  }

  // Defaults for convenience

  if (el("gs-start") && !el("gs-start").value) el("gs-start").value = _iso(_today);
  if (el("gs-end") && !el("gs-end").value) el("gs-end").value = _iso(_today);

  // Optional: kick off an empty search on load (comment if you prefer not to auto-run)
  // performGlobalSearch();

  // ----- Role detection & UI visibility -----
  let currentRole = "viewer"; // default; will be fetched
  const roleRank = { viewer: 0, user: 1, admin: 2 };

  function hasRole(required) {
    const r = (required || "viewer").toLowerCase();
    return (roleRank[currentRole] || 0) >= (roleRank[r] || 0);
  }

  async function detectRole() {
    const token = getToken();
    if (!token) {
      currentRole = "viewer";
      enforceRoleVisibility();
      const ri = document.getElementById("role-indicator");
      if (ri) ri.textContent = "Role: viewer (no token)";
      return "viewer";
    }
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { "X-Auth-Token": token }
      });
      if (res.status === 401) {
        currentRole = "viewer";
      } else {
        const json = await res.json();
        currentRole = (json.role || "viewer");
      }
    } catch (e) {
      currentRole = "viewer";
    }
    enforceRoleVisibility();
    const ri = document.getElementById("role-indicator");
    if (ri) ri.textContent = `Role: ${currentRole}`;
    return currentRole;
  }

  function enforceRoleVisibility() {
    // Hide or show any element annotated with data-requires-role
    document.querySelectorAll("[data-requires-role]").forEach(el => {
      const needed = el.getAttribute("data-requires-role") || "viewer";
      el.style.display = hasRole(needed) ? "" : "none";
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
  try {
    // Fill default dates if empty
    ['repstart','repend','sumstart','sumend','sum-start-create','sum-end-create'].forEach(id => {
      const input = document.getElementById(id);
      if (input && !input.value) input.value = todayISO();
    });

    // Event delegation for nav and primary actions
    document.addEventListener('click', (e) => {
      const a = e.target.closest('[data-action]');
      if (!a) return;

      const act = a.dataset.action;
      if (act === 'show-home') { e.preventDefault(); showView('home'); return; }
      if (act === 'show-reports') { e.preventDefault(); showView('reports'); loadDailyReport(); return; }
      if (act === 'show-sops') { e.preventDefault(); showView('sops'); loadSOPs(); return; }
      if (act === 'show-summaries') { e.preventDefault(); showView('summaries'); loadSummaries(); return; }
      if (act === 'show-settings') { e.preventDefault(); showView('settings'); return; }
      if (act === 'show-search') { e.preventDefault(); showView('search'); return; }

      if (act === 'do-search') { e.preventDefault(); performGlobalSearch(); return; }
      if (act === 'fetch-daily-report') { e.preventDefault(); loadDailyReport(); return; }
      if (act === 'fetch-weekly-report') { e.preventDefault(); loadWeeklyReport(); return; }
    });

    // Default landing view
    showView('home');
    console.log('[dashboard] initialized');
  } catch (err) {
    console.error('[dashboard] init error', err);
  }
});

  // ========= RBAC-FREE UI OVERRIDES =========

// Stop sending any auth headers
function getAuthHeaders() {
  return {}; // no X-Auth-Token
}

// If your code reads/saves a token in Settings, neutralize it
function loadSavedToken() {
  return ""; // pretend no token exists
}
function saveToken(_) {
  /* no-op */
}

// If your app does a role check or controls visibility, neutralize it
async function detectRoleAndSetupUI() {
  // Skip any /auth/me call, or if it exists elsewhere it will return {status:"ok", role:"public"}
  const role = "public";
  // Make everything visible; adjust selectors to your UI as needed
  try {
    document.querySelectorAll("[data-role-hide], [data-role], .role-gated").forEach(el => {
      el.style.display = ""; // unhide
      el.removeAttribute("data-role-hide");
    });
  } catch (e) { /* safe ignore */ }
  // If your code expects a return value:
  return { status: "ok", role };
}

// If your fetch wrappers rely on getAuthHeaders, nothing else is needed.
// For safety, ensure generic fetch wrappers do not attempt to add tokens:
async function apiGet(path) {
  const headers = { "Content-Type": "application/json", ...getAuthHeaders() };
  const res = await fetch(`${API_BASE}${path}`, { headers, method: "GET" });
  return res.json();
}
async function apiPost(path, body) {
  const headers = { "Content-Type": "application/json", ...getAuthHeaders() };
  const res = await fetch(`${API_BASE}${path}`, { headers, method: "POST", body: JSON.stringify(body) });
  return res.json();
}
// ========= END RBAC-FREE UI OVERRIDES =========

})();