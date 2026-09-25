# Handoff context — "Laut vorlesen in Berlin"

Rewritten 2026-09-25 for a move to a different Claude account. The previous
version of this file (2026-09-12) is badly stale by now — 61 commits and a
full design pass happened since. **Paste this whole file as your first
message in the new session**, and tell it to read `README.md` next (kept
current, ongoing, canonical — this file is just an orientation pointer +
what README doesn't cover).

## What this is, and where it lives

A scraper + static website listing Berlin book readings ("Lesungen"),
aggregated nightly from German publisher and venue websites. No backend —
GitHub Pages + a Python scraping pipeline that runs via a scheduled GitHub
Action and commits fresh data back to the repo on its own.

- **Repo:** https://github.com/frankerler/vorlesen (public)
- **Live site:** https://frankerler.github.io/vorlesen/
- **Admin page:** https://frankerler.github.io/vorlesen/web/admin.html
- **Local working copy:** `/Users/frank/Downloads/Dev/vorlesen` on this Mac
- Current state: 241 events, 21 active scrapers (8 publishers + 13 venues/
  institutions; one more, Ocelot, is deliberately disabled — see README's
  "Not scraped on principle" note), nightly crawl has been running
  unattended and finding new events on its own schedule.

## The actual question: moving to a different Claude account

**The project's files and the "Claude account" are two completely separate
things — nothing about the code is tied to which Claude account is used.**
What actually matters is *where the working directory lives*:

- **Same Mac, just a different Claude account:** there is nothing to
  "link" or transfer. The files are already sitting at
  `/Users/frank/Downloads/Dev/vorlesen` — just point the new Claude Code
  session at that same folder path and it has full access to everything
  (code, git history, local data) immediately. A GitHub Desktop-app
  "project" list entry, if you use one, is a separate, cosmetic thing from
  the actual folder — just open/add that path.
- **A different machine entirely:** then yes, the folder itself needs to
  exist there too. Since it's already a public GitHub repo, that's just:
  ```bash
  git clone https://github.com/frankerler/vorlesen.git
  cd vorlesen
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  ```
  Plus `gh auth login` (or however that machine authenticates to GitHub)
  if you want to push from there — see "gh account gotcha" below, this is
  a GitHub credential, not a Claude one, and is per-machine either way.

**What genuinely does not transfer, in either case, is this conversation.**
That's the entire reason this file exists — everything below is what I'd
otherwise have to re-explain from scratch.

## Key design decisions worth knowing before touching this

1. **No backend, ever, on principle.** Every write-capable feature routes
   around that: visitor suggestions → Formspree (see "still open" below);
   admin CRUD → a user-pasted GitHub token kept only in that browser's
   localStorage, never committed; nightly refresh → GitHub Actions' own
   built-in token, no personal PAT needed for the scheduled run itself.
2. **Cross-source de-duplication is fuzzy, not exact** (date + venue +
   author matching, accent-folded/punctuation-stripped) — see
   `merge_cross_source_duplicates()` in `run.py`. Catches things like the
   same reading being reported by both a publisher and the venue hosting
   it. One real bug found and fixed while building this: nearly every
   Berlin venue name contains the word "Berlin" itself, which was briefly
   causing false-positive venue matches until that word got added to the
   stripped-noise list in `normalize_venue()`.
3. **Past-dated events are dropped by default** (`run.py --include-past`
   to keep them for debugging) — some sources' own sitemaps leave stale
   event pages up long after the fact.
4. **Adding a new source is real scraper-engineering work, not a config
   toggle.** Each of the 21 active sources needed its own hand-built
   scraper against that specific site's actual structure (JSON-LD, an
   internal API, a JS blob embedded in the page, etc.) — there's no
   generic "just add a URL" path. `sources.json` only controls which
   *already-implemented* scrapers run.
5. **One source (Ocelot) is deliberately not scraped.** Its site sits
   behind an active anti-bot wall (a proof-of-work challenge) and its
   `robots.txt` explicitly disallows scraping tools by name — a
   deliberate signal from the operator, not just a technical hurdle, so
   it's logged as disabled in `sources.json` rather than worked around.

## Still open / worth asking about proactively

- **Formspree endpoint is still a placeholder.** `web/app.js` has
  `const FORMSPREE_ENDPOINT = "https://formspree.io/f/REPLACE_ME";` — the
  "+" suggest-a-reading button and the newsletter signup both show a clear
  "not connected yet" error instead of failing silently, but neither
  actually submits anywhere. This has been pending since the very first
  time it came up and is the one recurring loose end — worth checking on
  early in a new session rather than assuming it got resolved elsewhere.

## Operational gotchas hit while building this

- **Two `gh` accounts are logged in on this machine**
  (`frankerler` and `frankstaffbase`); the active one silently reverts to
  `frankstaffbase` between sessions/turns, causing `git push` to fail with
  a 403. Fix each time before pushing:
  ```bash
  gh auth switch --hostname github.com --user frankerler
  gh auth setup-git
  ```
- **The in-app Browser pane's access to `localhost` and even real external
  URLs has been inconsistent across sessions** — sometimes works,
  sometimes silently fails. When it doesn't: fall back to `curl` against a
  local `python3 -m http.server 8000` (run from the repo root) plus direct
  `node --check` / small Node.js snippets to test JS logic, and for
  GitHub-API-backed features, exercise the real API via `gh api` before
  trusting browser-side code that calls it.
- **`position: fixed` elements get their `display` "blockified"** per CSS
  spec (`inline-flex` reports as `flex` in `getComputedStyle`) — not a
  bug, just a gotcha when testing responsive `display: none` rules on
  fixed-position elements.
- A separate **cloud-based Claude Code session has also been working on
  this repo directly via GitHub PRs** (branch `claude/proceed-here-gyoh2b`,
  PRs #11 through #38 at last count: design overhaul, newsletter signup,
  share button, visitor counter, admin CRUD, mobile swipe view, ...).
  Worth `git pull`ing before starting any new work, and expect the repo to
  keep moving even between your own sessions.

## How to work on this locally

```bash
cd /Users/frank/Downloads/Dev/vorlesen
git pull                                    # catch up first -- see gotcha above
.venv/bin/python run.py --format both       # re-scrape everything, regenerate data/
python3 -m http.server 8000                 # serve the site locally
# open http://localhost:8000/web/index.html
```

To publish: commit, fix the `gh` account if needed (see above), `git
push`. GitHub Pages rebuilds automatically, usually within ~30–60s; poll
with `gh api repos/frankerler/vorlesen/pages/builds/latest --jq .status`
until it says `built`.

## Everything else

`README.md` at the repo root is the actively-maintained canonical
documentation — full sources table (all 21, with how each is scraped and
its known quirks/limitations), the admin page's exact capabilities, the
nightly crawl workflow, and step-by-step instructions for adding another
source. Read that for anything not covered above.
