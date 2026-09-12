# Handoff context — "Laut vorlesen in Berlin"

Written 2026-09-12 to resume this project in a new (cloud) conversation.
Paste this whole file as your first message there.

## What this is

A scraper + static website that lists book readings ("Lesungen") happening
in Berlin, aggregated from German publisher and venue websites. No backend
server — it's a GitHub Pages static site with a Python scraping pipeline
that runs nightly via GitHub Actions and commits fresh data back to the repo.

- **Repo:** https://github.com/frankerler/vorlesen (public, owned by GitHub
  account `frankerler`)
- **Live site:** https://frankerler.github.io/vorlesen/
- **Admin page:** https://frankerler.github.io/vorlesen/web/admin.html
- **Local dev root:** `/Users/frank/Downloads/Dev/vorlesen`
- Current data: 217 events across 11 sources (8 publishers + 3 independent
  Berlin literature venues).

## Architecture at a glance

```
scrapers/<name>.py   -- one module per source, each exposes scrape() -> list[Event]
scrapers/base.py     -- shared Event dataclass, HTTP fetch helper, date/quote-
                         extraction helpers, cross-source fuzzy-match helpers
sources.json          -- which scrapers are enabled/implemented (read by run.py)
run.py                -- orchestrator: runs enabled scrapers, filters to Berlin,
                         drops past-dated events, de-dupes (exact + fuzzy
                         cross-source), writes data/events.json + .csv
scripts/diff_events.py                 -- before/after event diff -> data/last_run.json
scripts/import_formspree_submissions.py -- folds a Formspree CSV export into events.json
.github/workflows/nightly-crawl.yml    -- runs run.py + diff_events.py nightly (02:00 UTC),
                                          auto-commits if anything changed
web/index.html, app.js, style.css     -- the public site (list view, mobile swipe view,
                                          search, quick date filters, suggest-a-reading form)
web/admin.html, admin.js, admin.css   -- admin CRUD tool (events, sources, crawl status)
data/events.json, events.csv          -- the actual dataset the site reads
data/last_run.json                    -- "what changed in the last crawl" summary
```

### The 11 sources (in `sources.json` / `run.py`'s `SCRAPERS`)

Publishers: Suhrkamp, Carl Hanser, Rowohlt, S. Fischer, Piper, dtv,
Kiepenheuer & Witsch, Ullstein.
Venues (host readings for many different publishers' authors): Literarisches
Colloquium Berlin (LCB), Literaturhaus Berlin ("Li-Be"), Lettrétage.

Each scraper was hand-built against that specific site's actual structure
(JSON-LD, embedded JSON blobs, internal APIs, or HTML parsing) — see
`README.md`'s per-source table for how each one works and its known
limitations (e.g. S. Fischer only exposes ~20 upcoming events without a
headless browser; Rowohlt's own sitemap used to leak stale past-dated event
pages, now filtered out by `run.py`).

## Key design decisions worth knowing before touching this

1. **Cross-source de-duplication is fuzzy, not exact.** The same reading
   often gets reported by both a publisher and the venue hosting it. See
   `merge_cross_source_duplicates()` in `run.py` + `venues_match()` /
   `authors_overlap()` in `scrapers/base.py`.
2. **Past-dated events are dropped by default** (`run.py`, `--include-past`
   to keep them for debugging).
3. **`book_title` is a separate field from `title`.** The UI headline shows
   just the book title; `title`/`raw_text` (when long enough to be real
   text, not a short category tag) becomes body-copy description in the
   detail view. Extraction quality varies by source — see README.
4. **No backend, ever.** Every write-capable feature routes around that
   constraint deliberately:
   - Visitor suggestions → POST to **Formspree** (no account needed, no
     secret exposed) — **NOT WIRED UP YET**, see "Open items" below.
   - Admin CRUD (edit/add/delete events, manage sources, trigger a crawl) →
     the admin page holds a **user-pasted GitHub personal access token in
     localStorage only** (never committed) and writes directly via the
     GitHub Contents/Actions REST API. Verified this exact request shape
     (create, update-with-sha, UTF-8/base64 round-trip) against the live
     API with a disposable test file before relying on it.
   - Nightly data refresh → GitHub Actions scheduled workflow, using the
     Action's own built-in token (no personal PAT needed for that).
5. **GitHub Pages project-site paths are relative, not root-absolute.**
   `web/app.js` fetches `../data/events.json` (not `/data/events.json`) so
   it works both locally and under the `/vorlesen/` subpath.

## Open items / things left mid-flight

- **Formspree endpoint is still a placeholder.** `web/app.js` has
  `const FORMSPREE_ENDPOINT = "https://formspree.io/f/REPLACE_ME";` — the
  "+" suggest-a-reading button shows a clear "not connected yet" error
  until the user signs up at formspree.io (I can't create that account for
  them) and pastes in the real endpoint. This has been pending for several
  turns — worth proactively asking about if picking this thread back up.
- No map view yet (frontend is list/swipe only).
- Coverage could expand: more publishers (Aufbau, C.H. Beck, Klett-Cotta,
  Hoffmann und Campe, DVA, Blessing, Luchterhand, ...) and venues
  (independent bookshops, Pfefferberg Theater, Urania, Deutsches Theater).
  Each new source needs its own scraper researched + written from scratch —
  there's no way to "just add a URL" generically (tried and confirmed this
  the hard way across 11 very differently-structured sites).

## Operational gotchas hit while building this

- **Two `gh` accounts are logged in on this machine** (`frankerler` and
  `frankstaffbase`); the active one silently reverts to `frankstaffbase`
  between turns sometimes, causing `git push` to fail with a 403. Fix each
  time: `gh auth switch --hostname github.com --user frankerler && gh auth
  setup-git`.
- **The in-app Browser pane can't navigate to `localhost`** in a fresh tab
  reliably in this environment — sometimes works, sometimes doesn't across
  sessions. When it fails, verification fell back to: `curl` against the
  local `python3 -m http.server 8000` (run from the repo root) plus direct
  `node --check` / Node.js logic tests of the JS, and for GitHub-API-backed
  features, exercising the real API via `gh api` before trusting the
  browser-side code. When it does work, `tabs_create` + `navigate` +
  `resize_window` (mobile preset or explicit width) + `javascript_tool` for
  synthetic touch/click events (since some actions time out on non-fronted
  tabs) has been the reliable combo.
- **`position: fixed` elements get their `display` "blockified"** per CSS
  spec (`inline-flex` becomes `flex` in `getComputedStyle`) — not a bug,
  just something to remember when testing responsive `display: none` rules
  on fixed-position elements.
- A stray **`data-view` toggle / swipe-view background color**: the
  requested swatch color earlier in the project was approximated visually
  (`#fb6376`) since there's no pixel-sampling tool available for pasted
  images — it was later reverted to white anyway.

## How to work on this locally

```bash
cd /Users/frank/Downloads/Dev/vorlesen
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # first time only
.venv/bin/python run.py --format both      # re-scrape everything, regenerate data/
python3 -m http.server 8000                 # serve the site locally
# open http://localhost:8000/web/index.html
```

To publish a change: commit, then (after fixing the `gh` account if needed)
`git push`. GitHub Pages rebuilds automatically, usually within ~30–60s;
poll with `gh api repos/frankerler/vorlesen/pages/builds/latest --jq
.status` until it says `built`.

To test the nightly crawl on demand: `gh workflow run nightly-crawl.yml
--repo frankerler/vorlesen`, then watch with `gh run list --repo
frankerler/vorlesen --workflow=nightly-crawl.yml --limit 1`.

## Full file map

See the tree in "Architecture at a glance" above, plus:
- `README.md` — the canonical, detailed project documentation (sources
  table, known limitations, admin page docs, "adding another
  publisher/venue" instructions). Read this first for anything not covered
  here.
- `requirements.txt` — Python deps (`requests`, `beautifulsoup4`, `lxml`,
  `python-dateutil`).
- `.claude/launch.json` — a dev-server launch config that doesn't actually
  work in this sandboxed environment (the launcher's own cwd resolution
  fails); use plain `python3 -m http.server 8000` instead.
