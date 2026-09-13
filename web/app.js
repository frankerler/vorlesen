(function () {
  "use strict";

  const listEl = document.getElementById("list");
  const emptyEl = document.getElementById("empty-state");
  const searchEl = document.getElementById("search");
  const resultCountEl = document.getElementById("result-count");
  const overlayEl = document.getElementById("overlay");
  const detailContentEl = document.getElementById("detail-content");
  const closeBtn = document.getElementById("close-detail");
  const shareBtn = document.getElementById("share-detail");
  const shareFeedbackEl = document.getElementById("share-feedback");

  const quickFiltersEl = document.getElementById("quick-filters");
  const controlsBarEl = document.getElementById("controls-bar");

  const suggestBtn = document.getElementById("suggest-btn");
  const suggestOverlayEl = document.getElementById("suggest-overlay");
  const closeSuggestBtn = document.getElementById("close-suggest");
  const suggestFormEl = document.getElementById("suggest-form");
  const suggestStatusEl = document.getElementById("suggest-status");
  const suggestSubmitBtn = suggestFormEl ? suggestFormEl.querySelector(".suggest-submit") : null;

  const newsletterWidgetEl = document.getElementById("newsletter-widget");
  const newsletterToggleBtn = document.getElementById("newsletter-toggle");
  const newsletterFormEl = document.getElementById("newsletter-form");
  const newsletterEmailInput = document.getElementById("newsletter-email");
  const newsletterCloseBtn = document.getElementById("newsletter-close");
  const newsletterStatusEl = document.getElementById("newsletter-status");
  const newsletterSubmitBtn = newsletterFormEl ? newsletterFormEl.querySelector(".newsletter-submit") : null;

  // TODO: replace with your real Formspree form endpoint (formspree.io ->
  // create a form -> copy the URL it gives you, looks like
  // "https://formspree.io/f/xxxxxxxx"). Submissions won't go anywhere until
  // this is set. Reused for both the reading-suggestion form and the
  // newsletter form -- each sets its own hidden "_subject" field so
  // submissions are distinguishable in the Formspree inbox/dashboard even
  // though they share one form (most Formspree plans only allow one).
  const FORMSPREE_ENDPOINT = "https://formspree.io/f/REPLACE_ME";

  const WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
  const MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
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

  // --- Shareable per-event links (?event=<id>) ---------------------------
  //
  // Lets the share button hand out a link that reopens this exact event
  // (rather than just the homepage), and lets the browser's own back/
  // forward navigation open/close the detail view in sync with the URL.

  function getEventIdFromUrl() {
    return new URLSearchParams(location.search).get("event");
  }

  function findEventById(id) {
    return allEvents.find((ev) => ev.id === id) || null;
  }

  function setEventInUrl(id, { replace = false } = {}) {
    const url = new URL(location.href);
    if (id) url.searchParams.set("event", id);
    else url.searchParams.delete("event");
    if (replace) history.replaceState({}, "", url);
    else history.pushState({}, "", url);
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

  // Recognized social/media hosts get a short, friendly label instead of the
  // raw URL; anything else falls back to its bare domain -- either way this
  // keeps a scraped description from being dominated by a long link.
  const LINK_LABELS = {
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "twitter.com": "Twitter/X",
    "x.com": "Twitter/X",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "tiktok.com": "TikTok",
  };

  function linkLabel(url) {
    let host;
    try {
      host = new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return "Link";
    }
    for (const domain in LINK_LABELS) {
      if (host === domain || host.endsWith(`.${domain}`)) return LINK_LABELS[domain];
    }
    return host;
  }

  // Turns bare "https://…" URLs inside plain text into short clickable
  // labels (e.g. a long Instagram link becomes just "Instagram") instead of
  // wrapping the raw URL across several lines. Everything else is escaped
  // as usual, so this is a safe drop-in replacement for escapeHtml() on
  // free-text fields that might contain a URL.
  const URL_RE = /https?:\/\/[^\s<>"]+/g;

  function linkifyText(text) {
    if (text == null) return "";
    const s = String(text);
    let out = "";
    let lastIndex = 0;
    let match;
    while ((match = URL_RE.exec(s))) {
      let url = match[0];
      // Strip trailing punctuation a naive URL match tends to swallow
      // (e.g. the period ending a sentence, or a closing bracket).
      let trail = "";
      while (url && /[.,;:!?)\]]$/.test(url)) {
        trail = url.slice(-1) + trail;
        url = url.slice(0, -1);
      }
      if (!url) continue;
      out += escapeHtml(s.slice(lastIndex, match.index));
      out += `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(linkLabel(url))}</a>`;
      out += escapeHtml(trail);
      lastIndex = match.index + match[0].length;
    }
    out += escapeHtml(s.slice(lastIndex));
    return out;
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

  // Venue name + street address together geocode more reliably than the
  // address alone (e.g. a bare "Kurfürstendamm 12" is ambiguous city-wide).
  function googleMapsUrl(ev) {
    const query = [ev.venue, ev.address].filter(Boolean).join(", ");
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
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

      const card = document.createElement("button");
      card.type = "button";
      card.className = "event-card";
      card.innerHTML = `
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

  // A handful of sources put a short event-type tag ("Lesung", "Premiere",
  // "Moderiertes Gespräch", ...) or a plain date/time string in raw_text
  // instead of real descriptive text -- both are always well under this
  // length, so this cutoff reliably separates "actual description" from
  // "not worth showing again" without a source-specific tag list.
  const MIN_DESCRIPTION_LENGTH = 40;

  function descriptionParts(ev) {
    const parts = [];
    const title = headline(ev);
    // The fuller original event text, when it adds information beyond the
    // (now book-title-only) headline above it.
    if (ev.title && ev.title !== title) parts.push(ev.title);
    if (ev.raw_text && ev.raw_text.length >= MIN_DESCRIPTION_LENGTH && !parts.includes(ev.raw_text)) {
      parts.push(ev.raw_text);
    }
    return parts;
  }

  // The list the currently open detail view is paging through, and the open
  // event's position in it -- so swiping up can step to "the next event in
  // the row" without needing to re-derive what that row was.
  let detailEvents = [];
  let detailIndex = -1;

  function renderDetailContent(ev) {
    const dt = parseDate(ev.date);
    const dateStr = dt ? `${WEEKDAYS[dt.getDay()]}, ${dt.getDate()}. ${MONTHS[dt.getMonth()]} ${dt.getFullYear()}` : "Datum unbekannt";

    const title = headline(ev);
    const description = descriptionParts(ev)
      .map((p) => `<p class="detail-description">${linkifyText(p)}</p>`)
      .join("");

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
        <dt>Adresse</dt><dd>${ev.address ? `<a href="${escapeHtml(googleMapsUrl(ev))}" target="_blank" rel="noopener noreferrer">${escapeHtml(ev.address)}</a>` : "–"}</dd>
      </dl>
      ${description}
      ${ev.url ? `<a class="detail-link" href="${escapeHtml(ev.url)}" target="_blank" rel="noopener noreferrer">Zur Veranstaltung / Tickets →</a>` : ""}
    `;
    overlayEl.scrollTop = 0;
  }

  function openDetail(ev, { skipUrlUpdate = false } = {}) {
    detailEvents = currentFilteredEvents;
    detailIndex = detailEvents.indexOf(ev);
    if (detailIndex === -1) {
      // A shared/deep-linked event might not be in the currently
      // filtered/searched list (e.g. it doesn't match the active quick
      // filter) -- fall back to a single-item list so swipe-to-next has
      // nothing to do, rather than breaking the view.
      detailEvents = [ev];
      detailIndex = 0;
    }
    renderDetailContent(ev);
    overlayEl.hidden = false;
    document.body.style.overflow = "hidden";
    if (!skipUrlUpdate) setEventInUrl(ev.id);
  }

  function closeDetail({ skipUrlUpdate = false } = {}) {
    overlayEl.hidden = true;
    document.body.style.overflow = "";
    if (!skipUrlUpdate) setEventInUrl(null);
  }

  // Swiping up steps to the next event in the same list the user opened this
  // one from -- but only from a scroll position at (or very near) the top,
  // so it doesn't hijack an ordinary scroll gesture while reading a long
  // description further down the page.
  function goToNextDetailEvent() {
    if (detailIndex < 0 || detailIndex + 1 >= detailEvents.length) return;
    detailContentEl.classList.add("detail-leaving");
    setTimeout(() => {
      detailIndex += 1;
      const ev = detailEvents[detailIndex];
      renderDetailContent(ev);
      detailContentEl.classList.remove("detail-leaving");
      // Replace, not push -- so swiping through several events doesn't
      // pile up a back-stack entry per step, but the URL still reflects
      // whichever event is currently on screen for sharing/reloading.
      setEventInUrl(ev.id, { replace: true });
    }, 160);
  }

  closeBtn.addEventListener("click", () => closeDetail());
  overlayEl.addEventListener("click", (e) => {
    if (e.target === overlayEl) closeDetail();
  });

  // --- Share button: hand off to the OS/browser's native share sheet
  // (copy link, Messages, WhatsApp, Mail, ...) where available, falling
  // back to copying the link to the clipboard everywhere else (most
  // desktop browsers don't implement navigator.share).

  function eventShareUrl(ev) {
    const url = new URL(location.href);
    url.search = "";
    url.searchParams.set("event", ev.id);
    return url.toString();
  }

  let shareFeedbackTimeout = null;

  function showShareFeedback(message) {
    shareFeedbackEl.textContent = message;
    shareFeedbackEl.hidden = false;
    clearTimeout(shareFeedbackTimeout);
    shareFeedbackTimeout = setTimeout(() => {
      shareFeedbackEl.hidden = true;
    }, 2200);
  }

  // A short, generic invite text to go along with the link -- shown in the
  // native share sheet's message preview, and prepended to the clipboard
  // fallback so pasting it somewhere brings the text along, not just the
  // bare URL.
  function shareMessage(ev) {
    return `Hier eine interessante Lesung: ${headline(ev)}`;
  }

  function copyShareLink(text, url) {
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      showShareFeedback("Kopieren nicht möglich");
      return;
    }
    navigator.clipboard
      .writeText(`${text}\n${url}`)
      .then(() => showShareFeedback("Link kopiert"))
      .catch(() => showShareFeedback("Kopieren fehlgeschlagen"));
  }

  function shareCurrentDetailEvent() {
    const ev = detailEvents[detailIndex];
    if (!ev) return;
    const url = eventShareUrl(ev);
    const text = shareMessage(ev);

    if (navigator.share) {
      // Deliberately not passing `url` as its own field: several share
      // targets (iOS Messages among them) drop the custom `text` entirely
      // and keep only the URL when both are given separately, generating
      // their own link-preview card instead -- inconsistently, since other
      // apps (Signal included) then show neither. Folding the link into
      // `text` as one string guarantees it survives as literal message
      // content everywhere, at the cost of some apps' auto-preview card.
      navigator.share({ title: headline(ev), text: `${text}\n${url}` }).catch((err) => {
        // AbortError just means the user closed the share sheet without
        // picking anything -- not worth reporting or falling back for.
        if (err && err.name !== "AbortError") copyShareLink(text, url);
      });
    } else {
      copyShareLink(text, url);
    }
  }

  shareBtn.addEventListener("click", shareCurrentDetailEvent);

  let detailTouchStartY = null;
  overlayEl.addEventListener(
    "touchstart",
    (e) => {
      detailTouchStartY = e.touches[0].clientY;
    },
    { passive: true }
  );
  overlayEl.addEventListener("touchend", (e) => {
    if (detailTouchStartY == null) return;
    const deltaY = e.changedTouches[0].clientY - detailTouchStartY;
    detailTouchStartY = null;
    const SWIPE_THRESHOLD = 50;
    if (deltaY < -SWIPE_THRESHOLD && overlayEl.scrollTop <= 4) goToNextDetailEvent();
  });

  document.addEventListener("keydown", (e) => {
    if (overlayEl.hidden) return;
    if (e.key === "ArrowUp") goToNextDetailEvent();
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
    else if (newsletterWidgetEl.classList.contains("is-open")) closeNewsletterWidget();
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

  // --- Newsletter signup widget --------------------------------------------
  //
  // A floating pill (bottom center) that morphs in place into a small email
  // input tile -- no modal/overlay, it just stays anchored at the bottom.
  // Same no-backend submission approach as the suggestion form above: POSTs
  // straight to Formspree. For now, subscriber addresses just accumulate in
  // the Formspree dashboard -- export them as CSV and run
  // scripts/import_newsletter_subscribers.py to fold new ones into
  // data/subscribers.json, which web/admin.html lists.

  // Cached once so closing can size the widget back to the button's natural
  // width without measuring a hidden (display:none) element, which would
  // read 0. The button's label is static, so this never goes stale.
  let newsletterCollapsedWidth = null;

  function measureNewsletterCollapsedWidth() {
    const width = newsletterToggleBtn.getBoundingClientRect().width;
    if (width > 0) {
      newsletterCollapsedWidth = width;
      newsletterWidgetEl.style.width = `${width}px`;
    }
  }

  function openNewsletterWidget() {
    newsletterStatusEl.hidden = true;
    newsletterWidgetEl.style.width = `${Math.min(window.innerWidth - 40, 340)}px`;
    newsletterWidgetEl.classList.add("is-open");
    newsletterToggleBtn.hidden = true;
    // Wait for the container to mostly finish widening before revealing the
    // input row -- showing it immediately would cram it into a box that's
    // still animating open from the button's much narrower starting width.
    setTimeout(() => {
      newsletterFormEl.hidden = false;
      newsletterEmailInput.focus();
    }, 220);
  }

  function closeNewsletterWidget() {
    newsletterWidgetEl.classList.remove("is-open");
    if (newsletterCollapsedWidth) newsletterWidgetEl.style.width = `${newsletterCollapsedWidth}px`;
    newsletterToggleBtn.hidden = false;
    newsletterFormEl.hidden = true;
    newsletterStatusEl.hidden = true;
  }

  measureNewsletterCollapsedWidth();
  newsletterToggleBtn.addEventListener("click", openNewsletterWidget);
  newsletterCloseBtn.addEventListener("click", closeNewsletterWidget);

  document.addEventListener("click", (e) => {
    if (newsletterWidgetEl.classList.contains("is-open") && !newsletterWidgetEl.contains(e.target)) {
      closeNewsletterWidget();
    }
  });

  function showNewsletterStatus(message, isError) {
    newsletterStatusEl.textContent = message;
    newsletterStatusEl.className = "newsletter-status" + (isError ? " newsletter-status--error" : "");
    newsletterStatusEl.hidden = false;
  }

  newsletterFormEl.addEventListener("submit", (e) => {
    e.preventDefault();

    if (FORMSPREE_ENDPOINT.includes("REPLACE_ME")) {
      showNewsletterStatus("Formular noch nicht angeschlossen (fehlender Formspree-Endpoint).", true);
      return;
    }

    const data = new FormData(newsletterFormEl);
    newsletterSubmitBtn.disabled = true;
    newsletterEmailInput.disabled = true;

    fetch(FORMSPREE_ENDPOINT, {
      method: "POST",
      body: data,
      headers: { Accept: "application/json" },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        showNewsletterStatus("Danke! Du bist jetzt angemeldet.", false);
        newsletterFormEl.reset();
        setTimeout(closeNewsletterWidget, 1600);
      })
      .catch(() => {
        showNewsletterStatus("Anmeldung fehlgeschlagen. Bitte versuch es gleich noch einmal.", true);
      })
      .finally(() => {
        newsletterSubmitBtn.disabled = false;
        newsletterEmailInput.disabled = false;
      });
  });

  let currentFilteredEvents = [];

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
    currentFilteredEvents = filtered;
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

    // Keep the detail view in sync with browser back/forward, without
    // re-pushing the history entry that got us here in the first place.
    const id = getEventIdFromUrl();
    const ev = id ? findEventById(id) : null;
    if (ev) openDetail(ev, { skipUrlUpdate: true });
    else closeDetail({ skipUrlUpdate: true });
  });

  highlightActiveQuickFilter();

  // --- Sticky controls bar: hide on scroll down, reveal on scroll up -----
  //
  // .controls-bar is `position: sticky`, so it only actually starts
  // sticking to the top once the page has scrolled past its natural
  // position (roughly the title's height). Below that point it's still
  // part of normal flow and should always stay visible; sliding it away
  // with a transform before then would just leave a blank gap where it
  // used to be. controlsStickyOffset tracks that threshold.
  let controlsStickyOffset = controlsBarEl.offsetTop;
  window.addEventListener("resize", () => {
    controlsStickyOffset = controlsBarEl.offsetTop;
  });

  let lastScrollY = window.scrollY;
  let scrollTicking = false;
  const SCROLL_DELTA_THRESHOLD = 4; // ignore sub-pixel/jitter scroll events

  function updateControlsBarVisibility() {
    const currentY = window.scrollY;
    const delta = currentY - lastScrollY;
    if (currentY <= controlsStickyOffset) {
      controlsBarEl.classList.remove("controls-hidden");
    } else if (delta > SCROLL_DELTA_THRESHOLD) {
      controlsBarEl.classList.add("controls-hidden"); // scrolling down -> hide
    } else if (delta < -SCROLL_DELTA_THRESHOLD) {
      controlsBarEl.classList.remove("controls-hidden"); // scrolling up -> reveal
    }
    lastScrollY = currentY;
    scrollTicking = false;
  }

  window.addEventListener(
    "scroll",
    () => {
      if (scrollTicking) return;
      scrollTicking = true;
      window.requestAnimationFrame(updateControlsBarVisibility);
    },
    { passive: true }
  );

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
      applyFilter();

      // Open straight to a shared/bookmarked event, if the URL names one.
      const deepLinkId = getEventIdFromUrl();
      const deepLinkEvent = deepLinkId ? findEventById(deepLinkId) : null;
      if (deepLinkEvent) openDetail(deepLinkEvent, { skipUrlUpdate: true });
    })
    .catch((err) => {
      listEl.innerHTML = `<p class="empty-state">Konnte Daten nicht laden: ${escapeHtml(err.message)}. Lief die Seite über einen lokalen Server (z. B. <code>python3 -m http.server</code>) und wurde <code>run.py</code> schon ausgeführt?</p>`;
    });
})();
