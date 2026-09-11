(function () {
  "use strict";

  const GITHUB_REPO = "frankerler/vorlesen";
  const API_URL = `https://api.github.com/repos/${GITHUB_REPO}/issues?labels=event-suggestion&state=open&per_page=100`;

  const listEl = document.getElementById("admin-list");
  const emptyEl = document.getElementById("admin-empty");
  const errorEl = document.getElementById("admin-error");

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Issue bodies are written by our own "suggest a reading" form as
  // "**Label:** value" lines (see web/app.js buildIssueBody) -- parse them
  // back out. Falls back gracefully (raw body shown) if someone opened the
  // issue manually on GitHub instead of through the form.
  function parseFields(body) {
    const fields = {};
    const re = /\*\*([^:*]+):\*\*\s*(.*)/g;
    let m;
    while ((m = re.exec(body || "")) !== null) {
      const key = m[1].trim().toLowerCase();
      const value = m[2].trim();
      fields[key] = value === "–" ? "" : value;
    }
    return fields;
  }

  const FIELD_MAP = [
    ["autor", "author"],
    ["buchtitel", "book_title"],
    ["veranstaltungsort", "venue"],
    ["adresse", "address"],
    ["datum", "date"],
    ["uhrzeit", "time"],
    ["link", "url"],
    ["anmerkungen", "notes"],
  ];

  function normalizeFields(raw) {
    const out = {};
    for (const [de, en] of FIELD_MAP) {
      if (raw[de] !== undefined) out[en] = raw[de];
    }
    return out;
  }

  function suggestionToEventJson(fields, issue) {
    return JSON.stringify(
      {
        publisher: "Community-Vorschlag",
        author: fields.author || null,
        title: fields.book_title || null,
        book_title: fields.book_title || null,
        date: fields.date || null,
        time: fields.time || null,
        venue: fields.venue || null,
        city: "Berlin",
        address: fields.address || null,
        url: fields.url || null,
        source_url: issue.html_url,
      },
      null,
      2
    );
  }

  function renderIssue(issue) {
    const raw = parseFields(issue.body);
    const fields = normalizeFields(raw);
    const hasParsedFields = Object.keys(fields).length > 0;

    const card = document.createElement("article");
    card.className = "suggestion-card";

    const createdAt = new Date(issue.created_at).toLocaleDateString("de-DE", {
      day: "2-digit", month: "long", year: "numeric",
    });

    card.innerHTML = `
      <h3><a href="${escapeHtml(issue.html_url)}" target="_blank" rel="noopener noreferrer">#${issue.number} · ${escapeHtml(issue.title)}</a></h3>
      <p class="suggestion-meta">Eingereicht von ${escapeHtml(issue.user?.login || "unbekannt")} am ${createdAt}</p>
      ${hasParsedFields ? `
        <dl class="suggestion-facts">
          <dt>Autor</dt><dd>${escapeHtml(fields.author || "–")}</dd>
          <dt>Buchtitel</dt><dd>${escapeHtml(fields.book_title || "–")}</dd>
          <dt>Ort</dt><dd>${escapeHtml(fields.venue || "–")}</dd>
          <dt>Adresse</dt><dd>${escapeHtml(fields.address || "–")}</dd>
          <dt>Datum</dt><dd>${escapeHtml(fields.date || "–")}${fields.time ? " · " + escapeHtml(fields.time) + " Uhr" : ""}</dd>
          <dt>Link</dt><dd>${fields.url ? `<a href="${escapeHtml(fields.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(fields.url)}</a>` : "–"}</dd>
          <dt>Anmerkungen</dt><dd>${escapeHtml(fields.notes || "–")}</dd>
        </dl>
      ` : `
        <p class="suggestion-parse-warning">Konnte die Felder nicht automatisch auslesen — vermutlich manuell auf GitHub erstellt. Bitte das Issue direkt öffnen.</p>
      `}
      <div class="suggestion-actions">
        <a class="primary" href="${escapeHtml(issue.html_url)}" target="_blank" rel="noopener noreferrer">Auf GitHub öffnen &amp; freigeben</a>
        ${hasParsedFields ? `<button type="button" data-copy-json>Als Event-JSON kopieren</button>` : ""}
      </div>
    `;

    if (hasParsedFields) {
      const copyBtn = card.querySelector("[data-copy-json]");
      copyBtn.addEventListener("click", () => {
        const json = suggestionToEventJson(fields, issue);
        navigator.clipboard.writeText(json).then(
          () => { copyBtn.textContent = "Kopiert ✓"; setTimeout(() => (copyBtn.textContent = "Als Event-JSON kopieren"), 1500); },
          () => { copyBtn.textContent = "Kopieren fehlgeschlagen"; }
        );
      });
    }

    return card;
  }

  listEl.innerHTML = '<p class="loading-state">Lade Vorschläge …</p>';

  fetch(API_URL, { headers: { Accept: "application/vnd.github+json" } })
    .then((r) => {
      if (!r.ok) throw new Error(`GitHub API: HTTP ${r.status}`);
      return r.json();
    })
    .then((issues) => {
      // The issues endpoint also returns pull requests; filter those out.
      const suggestions = issues.filter((i) => !i.pull_request);
      listEl.innerHTML = "";
      emptyEl.hidden = suggestions.length > 0;
      suggestions
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        .forEach((issue) => listEl.appendChild(renderIssue(issue)));
    })
    .catch((err) => {
      listEl.innerHTML = "";
      errorEl.hidden = false;
      errorEl.textContent = `Konnte Vorschläge nicht laden: ${err.message}. (Die öffentliche GitHub-API ist auf ~60 Anfragen/Stunde ohne Login begrenzt.)`;
    });
})();
