(function () {
  "use strict";

  const listEl = document.getElementById("list");
  const emptyEl = document.getElementById("empty-state");
  const searchEl = document.getElementById("search");
  const resultCountEl = document.getElementById("result-count");
  const footerCountEl = document.getElementById("footer-count");
  const overlayEl = document.getElementById("overlay");
  const detailContentEl = document.getElementById("detail-content");
  const closeBtn = document.getElementById("close-detail");

  const quickFiltersEl = document.getElementById("quick-filters");

  const suggestBtn = document.getElementById("suggest-btn");
  const suggestOverlayEl = document.getElementById("suggest-overlay");
  const closeSuggestBtn = document.getElementById("close-suggest");
  const suggestFormEl = document.getElementById("suggest-form");
  const suggestStatusEl = document.getElementById("suggest-status");
  const suggestSubmitBtn = suggestFormEl ? suggestFormEl.querySelector(".suggest-submit") : null;

  // TODO: replace with your real Formspree form endpoint (formspree.io ->
  // create a form -> copy the URL it gives you, looks like
  // "https://formspree.io/f/xxxxxxxx"). Submissions won't go anywhere until
  // this is set.
  const FORMSPREE_ENDPOINT = "https://formspree.io/f/REPLACE_ME";

  const WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
  const MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
  ];
  const MONTHS_SHORT = [
    "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
  ];

  let allEvents = [];

  function parseDate(iso) {
    if (!iso) return null;
    const [y, m, d] = iso.split("-").map(Number);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  }

  function toIso(dt) {
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
  }

  function todayIso() {
    return toIso(new Date());
  }

  function addDaysIso(iso, days) {
    const dt = parseDate(iso);
    dt.setDate(dt.getDate() + days);
    return toIso(dt);
  }

  // --- Quick date-range links (?when=today|week|month|all) ---------------
  //
  // "Nächste Woche"/"Nächster Monat" are rolling windows from today (today
  // + 6 / + 29 days), not calendar-aligned week/month boundaries -- for an
  // events list, "what's coming up in the next week" reads more usefully
  // than "next Mon-Sun" (which would exclude anything between now and the
  // following Monday).
  const VALID_WHEN = ["today", "week", "month", "all"];

  function getWhenFromUrl() {
    const value = new URLSearchParams(location.search).get("when");
    return VALID_WHEN.includes(value) ? value : "all";
  }

  let activeWhen = getWhenFromUrl();

  function matchesWhen(ev) {
    if (activeWhen === "all") return true;
    if (!ev.date) return false;
    const today = todayIso();
    if (activeWhen === "today") return ev.date === today;
    if (activeWhen === "week") return ev.date >= today && ev.date <= addDaysIso(today, 6);
    if (activeWhen === "month") return ev.date >= today && ev.date <= addDaysIso(today, 29);
    return true;
  }

  function highlightActiveQuickFilter() {
    quickFiltersEl.querySelectorAll("a").forEach((a) => {
      a.classList.toggle("active", a.dataset.when === activeWhen);
    });
  }

  function formatDateHeading(iso) {
    const dt = parseDate(iso);
    if (!dt) return "Datum unbekannt";
    return `${WEEKDAYS[dt.getDay()]}, ${dt.getDate()}. ${MONTHS[dt.getMonth()]} ${dt.getFullYear()}`;
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function coverThumb(ev, className) {
    if (ev.cover_image) {
      return `<img class="${className}" src="${escapeHtml(ev.cover_image)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'${className} placeholder',innerHTML:'📖'}))">`;
    }
    return `<div class="${className} placeholder">📖</div>`;
  }

  function locationLine(ev) {
    return [ev.venue, ev.city].filter(Boolean).join(", ");
  }

  // Prefer just the book's title as the headline (what this app is about);
  // fall back to the fuller event title/description when a clean book title
  // couldn't be isolated for that source (see scrapers/*.py `book_title`).
  function headline(ev) {
    return ev.book_title || ev.title || ev.author || "Lesung";
  }

  function renderList(events) {
    listEl.innerHTML = "";
    resultCountEl.textContent = `${events.length} von ${allEvents.length}`;
    emptyEl.hidden = events.length > 0;

    let lastDateKey = null;
    const frag = document.createDocumentFragment();

    events.forEach((ev) => {
      if (ev.date !== lastDateKey) {
        lastDateKey = ev.date;
        const heading = document.createElement("div");
        heading.className = "date-heading";
        heading.textContent = formatDateHeading(ev.date);
        frag.appendChild(heading);
      }

      const dt = parseDate(ev.date);
      const card = document.createElement("button");
      card.type = "button";
      card.className = "event-card";
      card.innerHTML = `
        <div class="date-badge">
          <span class="day">${dt ? dt.getDate() : "?"}</span>
          <span class="mon">${dt ? MONTHS_SHORT[dt.getMonth()] : ""}</span>
        </div>
        ${coverThumb(ev, "cover-thumb")}
        <div class="event-main">
          <p class="event-title">${escapeHtml(headline(ev))}</p>
          <p class="event-meta">${escapeHtml(ev.author || "")}<span class="sep">·</span>${escapeHtml(locationLine(ev))}${ev.time ? `<span class="sep">·</span>${escapeHtml(ev.time)} Uhr` : ""}</p>
        </div>
      `;
      card.addEventListener("click", () => openDetail(ev));
      frag.appendChild(card);
    });

    listEl.appendChild(frag);
  }

  function openDetail(ev) {
    const dt = parseDate(ev.date);
    const dateStr = dt ? `${WEEKDAYS[dt.getDay()]}, ${dt.getDate()}. ${MONTHS[dt.getMonth()]} ${dt.getFullYear()}` : "Datum unbekannt";

    const title = headline(ev);
    // Show the fuller original event text as body copy when it adds
    // information beyond the (now book-title-only) headline above it.
    const longText = ev.title && ev.title !== title ? ev.title : null;

    detailContentEl.innerHTML = `
      <div class="detail-header">
        ${coverThumb(ev, "detail-cover")}
        <div class="detail-heading">
          <h2>${escapeHtml(title)}</h2>
          ${ev.author ? `<p class="detail-author">${escapeHtml(ev.author)}</p>` : ""}
          <span class="publisher-tag">${escapeHtml(ev.publisher)}</span>
        </div>
      </div>
      <dl class="detail-facts">
        <dt>Datum</dt><dd>${escapeHtml(dateStr)}${ev.time ? ` · ${escapeHtml(ev.time)} Uhr` : ""}</dd>
        <dt>Ort</dt><dd>${escapeHtml(ev.venue || "–")}</dd>
        <dt>Adresse</dt><dd>${escapeHtml(ev.address || "–")}</dd>
      </dl>
      ${longText ? `<p class="detail-description">${escapeHtml(longText)}</p>` : ""}
      ${ev.url ? `<a class="detail-link" href="${escapeHtml(ev.url)}" target="_blank" rel="noopener noreferrer">Zur Veranstaltung / Tickets →</a>` : ""}
    `;
    overlayEl.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeDetail() {
    overlayEl.hidden = true;
    document.body.style.overflow = "";
  }

  closeBtn.addEventListener("click", closeDetail);
  overlayEl.addEventListener("click", (e) => {
    if (e.target === overlayEl) closeDetail();
  });

  // --- Suggest-a-reading form -------------------------------------------
  //
  // This is a static site with no backend of its own, so submissions POST
  // directly to Formspree (a third-party form backend) -- no account needed
  // for the visitor, no secrets exposed client-side (the endpoint below is
  // a public-safe submission target, not a credential). Formspree emails you
  // each submission and keeps a dashboard; approved ones get folded into
  // data/events.json via scripts/import_formspree_submissions.py.

  function openSuggest() {
    suggestStatusEl.hidden = true;
    suggestOverlayEl.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeSuggest() {
    suggestOverlayEl.hidden = true;
    document.body.style.overflow = "";
  }

  suggestBtn.addEventListener("click", openSuggest);
  closeSuggestBtn.addEventListener("click", closeSuggest);
  suggestOverlayEl.addEventListener("click", (e) => {
    if (e.target === suggestOverlayEl) closeSuggest();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!suggestOverlayEl.hidden) closeSuggest();
    else if (!overlayEl.hidden) closeDetail();
  });

  function showSuggestStatus(message, isError) {
    suggestStatusEl.textContent = message;
    suggestStatusEl.className = "suggest-status" + (isError ? " suggest-status--error" : " suggest-status--ok");
    suggestStatusEl.hidden = false;
  }

  suggestFormEl.addEventListener("submit", (e) => {
    e.preventDefault();

    if (FORMSPREE_ENDPOINT.includes("REPLACE_ME")) {
      showSuggestStatus("Das Formular ist noch nicht angeschlossen (fehlender Formspree-Endpoint).", true);
      return;
    }

    const data = new FormData(suggestFormEl);
    suggestSubmitBtn.disabled = true;
    suggestSubmitBtn.textContent = "Wird gesendet …";

    fetch(FORMSPREE_ENDPOINT, {
      method: "POST",
      body: data,
      headers: { Accept: "application/json" },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        showSuggestStatus("Danke! Dein Vorschlag wurde übermittelt und wird geprüft.", false);
        suggestFormEl.reset();
        setTimeout(closeSuggest, 1800);
      })
      .catch(() => {
        showSuggestStatus("Senden fehlgeschlagen. Bitte versuch es gleich noch einmal.", true);
      })
      .finally(() => {
        suggestSubmitBtn.disabled = false;
        suggestSubmitBtn.textContent = "Vorschlag absenden →";
      });
  });

  function applyFilter() {
    const q = searchEl.value.trim().toLowerCase();
    const filtered = allEvents.filter((ev) => {
      if (!matchesWhen(ev)) return false;
      if (!q) return true;
      const haystack = [ev.author, ev.title, ev.venue, ev.city, ev.publisher, ev.address]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
    renderList(filtered);
  }

  searchEl.addEventListener("input", applyFilter);

  // Intercept clicks so switching ranges doesn't reload the page/re-fetch
  // data, but the URL still updates (pushState) -- so each range stays a
  // real, shareable/bookmarkable link (e.g. index.html?when=week).
  quickFiltersEl.addEventListener("click", (e) => {
    const link = e.target.closest("a[data-when]");
    if (!link) return;
    e.preventDefault();
    activeWhen = link.dataset.when;
    const url = new URL(location.href);
    if (activeWhen === "all") url.searchParams.delete("when");
    else url.searchParams.set("when", activeWhen);
    history.pushState({}, "", url);
    highlightActiveQuickFilter();
    applyFilter();
  });

  window.addEventListener("popstate", () => {
    activeWhen = getWhenFromUrl();
    highlightActiveQuickFilter();
    applyFilter();
  });

  highlightActiveQuickFilter();

  // Relative (not root-absolute) so this works both from a local server at
  // the project root and from a GitHub Pages project site served under a
  // /<repo-name>/ subpath.
  fetch("../data/events.json")
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((data) => {
      allEvents = data;
      footerCountEl.textContent = `${data.length} Veranstaltungen`;
      applyFilter();
    })
    .catch((err) => {
      listEl.innerHTML = `<p class="empty-state">Konnte Daten nicht laden: ${escapeHtml(err.message)}. Lief die Seite über einen lokalen Server (z. B. <code>python3 -m http.server</code>) und wurde <code>run.py</code> schon ausgeführt?</p>`;
    });
})();
