# vorlesen — Berlin book reading / Lesung event scraper

Scrapes German publisher websites for author events (Lesungen, Buchpremieren,
Vorträge, etc.) and filters them down to events happening in Berlin.

It also includes a small static frontend ([web/](web/)) that reads
`data/events.json` and lets you browse and search the events.

## Web interface

```bash
# from the project root
python3 -m http.server 8000
```

Then open **http://localhost:8000/web/index.html** in your browser. It shows:

- a searchable list of all events (title, author, location, date), grouped by day
- a search box on top that filters live across author/title/venue/city/publisher
- clicking an entry opens a detail view with the full description, date/time,
  venue/address, a book cover image (where the source site has one), and a
  link to the original event/ticket page
- a **+** button (top right) for visitors to suggest a reading that's missing

Re-run `python run.py` whenever you want to refresh the data the page reads.

## Community suggestions

This is a static site (GitHub Pages) with no server or database, so a
visitor's browser can't safely write anywhere on its own — any write
credential placed in client-side JS would be visible to anyone who views
the page source. Submissions go through **[Formspree](https://formspree.io)**
instead, a third-party form backend built for exactly this:

1. The **+** button opens a form ([web/index.html](web/index.html));
   submitting it POSTs directly to a Formspree endpoint. No account needed
   for the visitor, no secrets exposed (the endpoint is a public-safe
   submission target, not a credential).
2. You review submissions in your [Formspree dashboard](https://formspree.io/login)
   (or the email notification it sends per submission) — see
   **[web/admin.html](web/admin.html)** for the exact steps.
3. Export the ones you want to keep as CSV from Formspree, then run:
   ```bash
   .venv/bin/python scripts/import_formspree_submissions.py submissions.csv            # import
   .venv/bin/python scripts/import_formspree_submissions.py submissions.csv --dry-run  # preview only
   ```
   There's no separate "approve" step in the tooling — the CSV you export
   *is* the approval; just delete rows you don't want before running it. The
   script appends new events to `data/events.json`/`.csv`; commit + push to
   publish.

**Setup required:** `FORMSPREE_ENDPOINT` in [web/app.js](web/app.js) is a
placeholder until a real Formspree form is created and its endpoint pasted
in — the form shows a clear error instead of failing silently until then.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```bash
# Scrape everything, write data/events.json
.venv/bin/python run.py

# Only some publishers
.venv/bin/python run.py --publisher rowohlt hanser

# Keep all cities instead of filtering to Berlin
.venv/bin/python run.py --all-cities

# Also write CSV
.venv/bin/python run.py --format both
```

Each event record looks like:

```json
{
  "publisher": "Suhrkamp Verlag",
  "author": "Lutz Seiler",
  "title": "Lutz Seiler liest aus seinem neuen Roman Das tickende Herz ...",
  "book_title": "Das tickende Herz",
  "date": "2026-10-14",
  "time": "20:00",
  "venue": "Pfefferberg Theater",
  "city": "Berlin",
  "address": "Schönhauser Alle 176, 10119 Berlin",
  "url": "https://www.suhrkamp.de/buchpremiere/lutz-seiler-v-50026",
  "source_url": "https://www.suhrkamp.de/veranstaltungen/alle-veranstaltungen-s-1113",
  "id": "da6957f6418b2cc8"
}
```

## Sources covered

### Publishers (8)

| Publisher | Module | How it's scraped |
|---|---|---|
| Suhrkamp Verlag | `scrapers/suhrkamp.py` | `__NEXT_DATA__` JSON blob, server-side `?city_ss=Berlin` filter + pagination |
| Carl Hanser Verlag | `scrapers/hanser.py` | Site's own internal `/api/events` JSON endpoint, filtered server-side |
| Rowohlt Verlag | `scrapers/rowohlt.py` | Events sitemap (`sitemap-events.xml`) → per-event JSON-LD |
| S. Fischer Verlage | `scrapers/fischer.py` | Listing page → per-event JSON-LD (capped at ~20 upcoming, see below) |
| Piper Verlag | `scrapers/piper.py` | Full server-rendered listing (`data-town` attrs) → detail page for venue/time |
| dtv Verlag | `scrapers/dtv.py` | schema.org/Event microdata, server-side `?city=Berlin` filter + pagination |
| Kiepenheuer & Witsch | `scrapers/kiwi.py` | Direct query to the site's own public *search-only* Algolia index |
| Ullstein Verlag | `scrapers/ullstein.py` | `__NEXT_DATA__` JSON blob (full Algolia dataset), paginated |

### Venues (3)

Independent Berlin reading venues that host events for many different
publishers' authors, rather than just their own:

| Venue | Module | How it's scraped |
|---|---|---|
| Literarisches Colloquium Berlin (LCB) | `scrapers/lcb.py` | Listing page → detail page's labelled sidebar (date/venue/participants) |
| Literaturhaus Berlin ("Li-Be") | `scrapers/literaturhaus.py` | Server-rendered listing page + a venue-address lookup page |
| Lettrétage | `scrapers/lettretage.py` | Listing page → per-event JSON-LD + free-text author extraction |

Every scraper returns a list of `Event` objects (see `scrapers/base.py`); `run.py`
merges them all, filters for Berlin, de-duplicates, sorts by date, and writes
the output files.

### Cross-source de-duplication

The same reading is often reported by *two* sources at once — e.g. a
Suhrkamp author's event at LCB shows up both in Suhrkamp's own scrape (as a
venue string) and in LCB's own venue scrape. Since the two sources rarely
agree on exact spelling, `run.py`'s `merge_cross_source_duplicates()` groups
events by date and fuzzy-matches venue + author (accent-folding, punctuation
stripping, name-token overlap — see `scrapers/base.py`'s `venues_match()` /
`authors_overlap()`), then keeps whichever record is more complete (has a
real cover image, address, etc.) instead of listing both.

## Known limitations

- **S. Fischer Verlage** only exposes its ~20 soonest events without a headless
  browser (their "load more" is pure client-side JS/Algolia) — so its Berlin
  coverage is shallower than the others.
- Every scraper depends on the current HTML/JSON structure of that publisher's
  site. If a publisher redesigns their site, that one scraper will need
  updating — it won't take down the others (`run.py` catches per-scraper
  exceptions and continues).
- Some publishers (e.g. Suhrkamp) label multi-person events with a
  descriptive phrase rather than a single clean author name — that's a
  quirk of the source data itself, not a parsing bug.
- Cross-source de-duplication is fuzzy (date + venue + author matching), not
  exact — it can occasionally miss a real duplicate (if the venue/author
  strings differ too much) or, in theory, merge two different events that
  happen to share a date, similar venue, and an overlapping name.
- Not scheduled/automated yet — re-run `run.py` manually (or add a cron job /
  GitHub Action) to refresh.
- Cover images: available for Piper, dtv, Rowohlt, S. Fischer, Hanser, KiWi,
  Ullstein, and Lettrétage. Suhrkamp, LCB, and Literaturhaus Berlin don't
  expose real book covers, so those events show a 📖 placeholder in the UI
  instead.
- LCB and Lettrétage often don't have a clean single "author" field on their
  own (a venue lists all participants/moderators, not just the book's
  author) — author is best-effort there and sometimes `null`.
- `book_title` (used as the headline in the UI instead of the full event
  description) is populated directly from clean source data where available
  (Hanser, KiWi, Ullstein, Literaturhaus: 100% coverage), and by best-effort
  extraction of a quoted/guillemet phrase from free text elsewhere. Overall
  ~74% of current events have one; when it's `null` the UI falls back to
  showing the full title. Rowohlt is the weakest source for this (its
  description text is plot-summary blurb that never quotes the book's own
  title) and Lettrétage/Literaturhaus-Berlin's one live event genuinely
  aren't book readings, so `null` is expected there.
- Literaturhaus Berlin's current listing ("Li-Be") only has one published
  event right now — the venue is mid-renovation and toured other locations
  under a different program until reopening; the scraper itself has no
  fixed-count assumption, so it'll pick up more once they're published.

## Adding another publisher or venue

1. Add `"module_name": "Display Name"` to `SCRAPERS` in `run.py`.
2. Create `scrapers/module_name.py` exposing `scrape() -> list[Event]`
   (see any existing scraper for the pattern — `scrapers/base.py` has the
   shared `Event` dataclass and helpers).
3. Run `.venv/bin/python -m scrapers.module_name` directly to test it in
   isolation before wiring it into the full pipeline.
4. For a venue (rather than a publisher), reuse the `publisher` field for
   the venue's own name — `merge_cross_source_duplicates()` in `run.py`
   already handles collapsing it against a matching publisher-sourced event.

## Next steps (not built yet)

- A map view (the current frontend is list-only).
- Scheduling (cron/GitHub Actions) to keep the data fresh.
- More publishers (Aufbau, C.H. Beck, Klett-Cotta, Hoffmann und Campe, DVA,
  Blessing, Luchterhand, ...) and more venues (independent bookshops,
  Pfefferberg Theater, Urania, Deutsches Theater, ...) for better coverage.
