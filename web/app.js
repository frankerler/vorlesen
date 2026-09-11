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
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !overlayEl.hidden) closeDetail();
  });

  function applyFilter() {
    const q = searchEl.value.trim().toLowerCase();
    if (!q) {
      renderList(allEvents);
      return;
    }
    const filtered = allEvents.filter((ev) => {
      const haystack = [ev.author, ev.title, ev.venue, ev.city, ev.publisher, ev.address]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
    renderList(filtered);
  }

  searchEl.addEventListener("input", applyFilter);

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
      renderList(allEvents);
    })
    .catch((err) => {
      listEl.innerHTML = `<p class="empty-state">Konnte Daten nicht laden: ${escapeHtml(err.message)}. Lief die Seite über einen lokalen Server (z. B. <code>python3 -m http.server</code>) und wurde <code>run.py</code> schon ausgeführt?</p>`;
    });
})();
