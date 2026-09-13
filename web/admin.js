(function () {
  "use strict";

  const OWNER = "frankerler";
  const REPO = "vorlesen";
  const BRANCH = "main";
  const WORKFLOW_FILE = "nightly-crawl.yml";
  const TOKEN_KEY = "vorlesen_admin_token";

  const API = `https://api.github.com/repos/${OWNER}/${REPO}`;

  // ---------------------------------------------------------------------
  // GitHub API client. The token lives only in this browser's localStorage
  // -- never committed, never sent anywhere but api.github.com.
  // ---------------------------------------------------------------------

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }

  function authHeaders() {
    const token = getToken();
    return token
      ? { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" }
      : { Accept: "application/vnd.github+json" };
  }

  function utf8ToBase64(str) {
    const bytes = new TextEncoder().encode(str);
    let binary = "";
    bytes.forEach((b) => (binary += String.fromCharCode(b)));
    return btoa(binary);
  }

  function base64ToUtf8(b64) {
    const binary = atob(b64.replace(/\n/g, ""));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }

  async function ghRequest(path, options = {}) {
    const resp = await fetch(`${API}${path}`, {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
    });
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(`GitHub API ${resp.status} on ${path}: ${body.slice(0, 300)}`);
    }
    return resp.status === 204 ? null : resp.json();
  }

  async function ghGetFile(filePath) {
    try {
      const data = await ghRequest(`/contents/${filePath}?ref=${BRANCH}`);
      return { text: base64ToUtf8(data.content), sha: data.sha };
    } catch (err) {
      if (String(err.message).includes(" 404 ")) return { text: null, sha: null };
      throw err;
    }
  }

  async function ghPutFile(filePath, text, message, sha) {
    return ghRequest(`/contents/${filePath}`, {
      method: "PUT",
      body: JSON.stringify({
        message,
        content: utf8ToBase64(text),
        branch: BRANCH,
        ...(sha ? { sha } : {}),
      }),
    });
  }

  async function ghGetUser() {
    const resp = await fetch("https://api.github.com/user", { headers: authHeaders() });
    if (!resp.ok) throw new Error(`Token ungültig oder ohne Zugriff (HTTP ${resp.status})`);
    return resp.json();
  }

  async function ghTriggerWorkflow() {
    return ghRequest(`/actions/workflows/${WORKFLOW_FILE}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: BRANCH }),
    });
  }

  async function ghLatestRun() {
    const data = await ghRequest(`/actions/workflows/${WORKFLOW_FILE}/runs?per_page=1&branch=${BRANCH}`);
    return (data.workflow_runs || [])[0] || null;
  }

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function showStatus(el, message, isError) {
    el.textContent = message;
    el.className = "suggest-status" + (isError ? " suggest-status--error" : " suggest-status--ok");
    el.hidden = false;
  }

  function newLocalId() {
    return (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`).replace(/-/g, "").slice(0, 16);
  }

  const EVENT_FIELDS = [
    "publisher", "author", "title", "date", "time", "venue", "city",
    "address", "url", "source_url", "raw_text", "cover_image", "image_credit", "book_title", "id",
  ];

  function eventsToCsv(events) {
    const esc = (v) => {
      if (v == null) return "";
      const s = String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [EVENT_FIELDS.join(",")];
    for (const e of events) lines.push(EVENT_FIELDS.map((f) => esc(e[f])).join(","));
    return lines.join("\n") + "\n";
  }

  // ---------------------------------------------------------------------
  // Connection UI
  // ---------------------------------------------------------------------

  const connectedEl = document.getElementById("connect-connected");
  const disconnectedEl = document.getElementById("connect-disconnected");
  const connectedUserEl = document.getElementById("connected-user");
  const connectErrorEl = document.getElementById("connect-error");
  const tokenInputEl = document.getElementById("token-input");

  const writeGatedButtons = [
    document.getElementById("crawl-now-btn"),
    document.getElementById("save-sources-btn"),
    document.getElementById("save-events-btn"),
  ];

  function setConnectedState(isConnected) {
    connectedEl.hidden = !isConnected;
    disconnectedEl.hidden = isConnected;
    writeGatedButtons.forEach((btn) => {
      btn.disabled = !isConnected;
      btn.title = isConnected ? "" : "Verbinde dich zuerst mit GitHub";
    });
  }

  async function tryConnect(token) {
    setToken(token);
    try {
      const user = await ghGetUser();
      connectedUserEl.textContent = user.login;
      connectErrorEl.hidden = true;
      setConnectedState(true);
    } catch (err) {
      clearToken();
      setConnectedState(false);
      showStatus(connectErrorEl, err.message, true);
    }
  }

  document.getElementById("connect-btn").addEventListener("click", () => {
    const token = tokenInputEl.value.trim();
    if (token) tryConnect(token);
  });

  document.getElementById("disconnect-btn").addEventListener("click", () => {
    clearToken();
    setConnectedState(false);
    tokenInputEl.value = "";
  });

  // ---------------------------------------------------------------------
  // Last run / crawl-now
  // ---------------------------------------------------------------------

  const lastRunInfoEl = document.getElementById("last-run-info");
  const crawlNowBtn = document.getElementById("crawl-now-btn");
  const crawlStatusEl = document.getElementById("crawl-status");

  function renderLastRun(summary) {
    if (!summary) {
      lastRunInfoEl.textContent = "Noch kein automatischer Crawl gelaufen.";
      return;
    }
    const when = new Date(summary.ran_at).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
    const newList = (summary.new_events || [])
      .map((e) => `<li>${escapeHtml(e.author)} — ${escapeHtml(e.book_title)} (${escapeHtml(e.date)}, ${escapeHtml(e.venue || "")})</li>`)
      .join("");
    lastRunInfoEl.innerHTML = `
      <p><strong>${when}</strong> · ${summary.total_events} Veranstaltungen insgesamt ·
      ${summary.new_count > 0 ? `<strong>${summary.new_count} neu 🎉</strong>` : "keine neuen"}</p>
      ${newList ? `<ul class="admin-new-events">${newList}</ul>` : ""}
    `;
  }

  fetch("../data/last_run.json")
    .then((r) => (r.ok ? r.json() : null))
    .then(renderLastRun)
    .catch(() => renderLastRun(null));

  crawlNowBtn.addEventListener("click", async () => {
    crawlNowBtn.disabled = true;
    try {
      await ghTriggerWorkflow();
      showStatus(crawlStatusEl, "Crawl gestartet — dauert ein paar Minuten. Fortschritt: siehe GitHub Actions.", false);
    } catch (err) {
      showStatus(crawlStatusEl, err.message, true);
    } finally {
      crawlNowBtn.disabled = !getToken();
    }
  });

  // ---------------------------------------------------------------------
  // Sources
  // ---------------------------------------------------------------------

  const sourcesTbodyEl = document.getElementById("sources-tbody");
  const sourcesStatusEl = document.getElementById("sources-status");
  let sourcesConfig = { sources: [] };
  let sourcesSha = null;

  function renderSources() {
    sourcesTbodyEl.innerHTML = "";
    sourcesConfig.sources.forEach((s, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><input type="checkbox" data-idx="${idx}" data-action="toggle" ${s.enabled ? "checked" : ""}></td>
        <td>${escapeHtml(s.label)} <code>${escapeHtml(s.id)}</code></td>
        <td>${s.type === "venue" ? "Veranstaltungsort" : "Verlag"}</td>
        <td>${s.implemented === false ? "⏳ noch nicht implementiert" : "✅ aktiv im Code"}</td>
        <td><button type="button" data-idx="${idx}" data-action="delete" class="link-btn">Entfernen</button></td>
      `;
      sourcesTbodyEl.appendChild(tr);
    });
  }

  sourcesTbodyEl.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const idx = Number(btn.dataset.idx);
    if (btn.dataset.action === "toggle") {
      sourcesConfig.sources[idx].enabled = btn.checked;
    } else if (btn.dataset.action === "delete") {
      if (confirm(`"${sourcesConfig.sources[idx].label}" wirklich entfernen?`)) {
        sourcesConfig.sources.splice(idx, 1);
        renderSources();
      }
    }
  });

  document.getElementById("add-source-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    if (sourcesConfig.sources.some((s) => s.id === data.id)) {
      alert(`Eine Quelle mit der ID "${data.id}" existiert schon.`);
      return;
    }
    sourcesConfig.sources.push({
      id: data.id, label: data.label, type: data.type, url: data.url || undefined,
      enabled: false, implemented: false,
    });
    renderSources();
    e.target.reset();
  });

  document.getElementById("save-sources-btn").addEventListener("click", async () => {
    try {
      const text = JSON.stringify(sourcesConfig, null, 2) + "\n";
      const result = await ghPutFile("sources.json", text, "Update sources.json via admin page", sourcesSha);
      sourcesSha = result.content.sha;
      showStatus(sourcesStatusEl, "Gespeichert ✓", false);
    } catch (err) {
      showStatus(sourcesStatusEl, err.message, true);
    }
  });

  async function loadSources() {
    // Public read -- no auth needed, works even before connecting.
    const resp = await fetch("../sources.json");
    const text = await resp.text();
    sourcesConfig = JSON.parse(text);
    renderSources();
    // Grab the SHA too (via API) so we can save later once connected.
    try {
      const { sha } = await ghGetFile("sources.json");
      sourcesSha = sha;
    } catch {
      /* not connected yet; sha will be fetched again on save if needed */
    }
  }

  // ---------------------------------------------------------------------
  // Events CRUD
  // ---------------------------------------------------------------------

  const eventsTbodyEl = document.getElementById("events-tbody");
  const eventsCountEl = document.getElementById("events-count");
  const eventsSearchEl = document.getElementById("events-search");
  const eventsStatusEl = document.getElementById("events-status");
  const pendingChangesEl = document.getElementById("pending-changes");
  const saveEventsBtn = document.getElementById("save-events-btn");

  const eventOverlayEl = document.getElementById("event-overlay");
  const eventFormEl = document.getElementById("event-form");
  const eventFormTitleEl = document.getElementById("event-form-title");

  let events = [];
  let eventsSha = null;
  let dirty = false;

  function markDirty() {
    dirty = true;
    pendingChangesEl.textContent = "•";
  }

  function renderEvents() {
    const q = eventsSearchEl.value.trim().toLowerCase();
    const filtered = !q
      ? events
      : events.filter((ev) =>
          [ev.author, ev.title, ev.book_title, ev.venue, ev.publisher]
            .filter(Boolean)
            .join(" ")
            .toLowerCase()
            .includes(q)
        );

    eventsCountEl.textContent = events.length;
    eventsTbodyEl.innerHTML = "";
    filtered.forEach((ev) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(ev.date)}</td>
        <td>${escapeHtml(ev.author)}</td>
        <td>${escapeHtml(ev.book_title || ev.title)}</td>
        <td>${escapeHtml(ev.venue)}</td>
        <td>${escapeHtml(ev.publisher)}</td>
        <td>
          <button type="button" class="link-btn" data-action="edit" data-id="${escapeHtml(ev.id)}">Bearbeiten</button>
          <button type="button" class="link-btn" data-action="delete" data-id="${escapeHtml(ev.id)}">Löschen</button>
        </td>
      `;
      eventsTbodyEl.appendChild(tr);
    });
  }

  eventsSearchEl.addEventListener("input", renderEvents);

  eventsTbodyEl.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const ev = events.find((x) => x.id === btn.dataset.id);
    if (!ev) return;
    if (btn.dataset.action === "edit") {
      openEventForm(ev);
    } else if (btn.dataset.action === "delete") {
      if (confirm(`"${ev.book_title || ev.title}" wirklich löschen?`)) {
        events = events.filter((x) => x.id !== ev.id);
        markDirty();
        renderEvents();
      }
    }
  });

  function openEventForm(ev) {
    eventFormTitleEl.textContent = ev ? "Veranstaltung bearbeiten" : "Neue Veranstaltung";
    eventFormEl.reset();
    if (ev) {
      for (const [key, value] of Object.entries(ev)) {
        const field = eventFormEl.elements.namedItem(key);
        if (field) field.value = value || "";
      }
    } else {
      eventFormEl.elements.namedItem("id").value = "";
    }
    eventOverlayEl.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeEventForm() {
    eventOverlayEl.hidden = true;
    document.body.style.overflow = "";
  }

  document.getElementById("add-event-btn").addEventListener("click", () => openEventForm(null));
  document.getElementById("close-event-form").addEventListener("click", closeEventForm);
  eventOverlayEl.addEventListener("click", (e) => {
    if (e.target === eventOverlayEl) closeEventForm();
  });

  eventFormEl.addEventListener("submit", (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(eventFormEl).entries());
    const isNew = !data.id;
    const eventData = {
      publisher: data.publisher || "Admin",
      author: data.author,
      title: data.book_title,
      book_title: data.book_title,
      date: data.date,
      time: data.time || null,
      venue: data.venue || null,
      city: "Berlin",
      address: data.address || null,
      url: data.url || null,
      source_url: isNew ? "admin" : undefined,
      raw_text: null,
      cover_image: data.cover_image || null,
      image_credit: data.image_credit || null,
      id: data.id || newLocalId(),
    };

    if (isNew) {
      events.push(eventData);
    } else {
      const idx = events.findIndex((x) => x.id === data.id);
      if (idx !== -1) events[idx] = { ...events[idx], ...eventData };
    }
    markDirty();
    renderEvents();
    closeEventForm();
  });

  saveEventsBtn.addEventListener("click", async () => {
    try {
      const sorted = [...events].sort((a, b) => (a.date || "9999").localeCompare(b.date || "9999"));
      const jsonText = JSON.stringify(sorted, null, 2) + "\n";
      const result = await ghPutFile("data/events.json", jsonText, "Update events.json via admin page", eventsSha);
      eventsSha = result.content.sha;

      const csvResult = await ghGetFile("data/events.csv");
      const csvText = eventsToCsv(sorted);
      await ghPutFile("data/events.csv", csvText, "Update events.csv via admin page", csvResult.sha);

      dirty = false;
      pendingChangesEl.textContent = "0";
      showStatus(eventsStatusEl, "Gespeichert ✓ — live in ein paar Sekunden auf GitHub Pages.", false);
    } catch (err) {
      showStatus(eventsStatusEl, err.message, true);
    }
  });

  async function loadEvents() {
    const resp = await fetch("../data/events.json");
    events = await resp.json();
    renderEvents();
    try {
      const { sha } = await ghGetFile("data/events.json");
      eventsSha = sha;
    } catch {
      /* fetched again on save if needed */
    }
  }

  // ---------------------------------------------------------------------
  // Newsletter subscribers (read-only -- see scripts/import_newsletter_subscribers.py)
  // ---------------------------------------------------------------------

  const subscribersCountEl = document.getElementById("subscribers-count");
  const subscribersTbodyEl = document.getElementById("subscribers-tbody");

  function renderSubscribers(subscribers) {
    subscribersCountEl.textContent = String(subscribers.length);
    subscribersTbodyEl.innerHTML = subscribers
      .map((s) => {
        const when = s.subscribed_at
          ? new Date(s.subscribed_at).toLocaleDateString("de-DE", { dateStyle: "medium" })
          : "–";
        return `<tr><td>${escapeHtml(s.email)}</td><td>${escapeHtml(when)}</td></tr>`;
      })
      .join("");
  }

  function loadSubscribers() {
    fetch("../data/subscribers.json")
      .then((r) => (r.ok ? r.json() : []))
      .then(renderSubscribers)
      .catch(() => renderSubscribers([]));
  }

  // ---------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------

  const existingToken = getToken();
  if (existingToken) {
    tryConnect(existingToken);
  } else {
    setConnectedState(false);
  }

  loadSources();
  loadEvents();
  loadSubscribers();
})();
