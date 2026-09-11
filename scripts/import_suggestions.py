#!/usr/bin/env python3
"""Fold approved community-suggested readings into data/events.json.

Workflow this script is part of:
1. A visitor uses the "+" button on the site to open a pre-filled GitHub
   issue (label: event-suggestion) -- see web/app.js.
2. You review it on GitHub (or via web/admin.html, which just reads the
   public issue list) and add the "approved" label once it looks right.
3. Run this script. It finds open issues labeled BOTH event-suggestion and
   approved, parses the "**Feld:** Wert" lines the form writes, appends them
   to data/events.json (and .csv), and closes each imported issue with a
   comment so it isn't picked up again.

Requires the `gh` CLI, authenticated with write access to the repo (this
needs real repo write access, unlike the read-only public API the admin
page uses -- that's why this is a script you run yourself, not something
baked into the static site).

Usage:
    .venv/bin/python scripts/import_suggestions.py            # import + close issues
    .venv/bin/python scripts/import_suggestions.py --dry-run  # preview only, no writes
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.base import Event  # noqa: E402

REPO = "frankerler/vorlesen"
DATA_DIR = Path(__file__).parent.parent / "data"
EVENTS_JSON = DATA_DIR / "events.json"
EVENTS_CSV = DATA_DIR / "events.csv"

FIELD_MAP = {
    "autor": "author",
    "buchtitel": "book_title",
    "veranstaltungsort": "venue",
    "adresse": "address",
    "datum": "date",
    "uhrzeit": "time",
    "link": "url",
    "anmerkungen": "notes",
}

FIELD_LINE_RE = re.compile(r"\*\*([^:*]+):\*\*\s*(.*)")


def gh_json(*args: str) -> list | dict:
    result = subprocess.run(["gh", *args, "--json", "number,title,body,url"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"gh command failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def parse_fields(body: str) -> dict:
    raw = {}
    for line in body.splitlines():
        m = FIELD_LINE_RE.match(line.strip())
        if m:
            key = m.group(1).strip().lower()
            value = m.group(2).strip()
            raw[key] = None if value == "–" else value
    return {en: raw.get(de) for de, en in FIELD_MAP.items()}


def issue_to_event(issue: dict) -> Event | None:
    fields = parse_fields(issue.get("body") or "")
    if not fields.get("author") or not fields.get("book_title") or not fields.get("date"):
        print(f"  [skip] #{issue['number']} '{issue['title']}' -- missing required fields (author/book_title/date)")
        return None

    return Event(
        publisher="Community-Vorschlag",
        author=fields["author"],
        title=fields["book_title"],
        date=fields["date"],
        time=fields.get("time"),
        venue=fields.get("venue"),
        city="Berlin",
        address=fields.get("address"),
        url=fields.get("url"),
        source_url=issue["url"],
        raw_text=fields.get("notes"),
        book_title=fields["book_title"],
    )


def load_existing_events() -> list[dict]:
    if not EVENTS_JSON.exists():
        return []
    return json.loads(EVENTS_JSON.read_text(encoding="utf-8"))


def write_events(events: list[dict]) -> None:
    events = sorted(events, key=lambda e: (e.get("date") or "9999-99-99", e.get("author") or ""))
    EVENTS_JSON.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [f.name for f in dataclasses.fields(Event)] + ["id"]
    with EVENTS_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for e in events:
            writer.writerow({k: e.get(k) for k in fieldnames})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be imported without writing or closing issues")
    args = parser.parse_args()

    print("Fetching approved suggestions from GitHub...")
    issues = gh_json(
        "issue", "list", "--repo", REPO,
        "--label", "event-suggestion", "--label", "approved",
        "--state", "open", "--limit", "200",
    )

    if not issues:
        print("No approved suggestions waiting to be imported.")
        return

    existing = load_existing_events()
    existing_ids = {e["id"] for e in existing}

    imported = []
    for issue in issues:
        event = issue_to_event(issue)
        if event is None:
            continue
        event_dict = event.to_dict()
        if event_dict["id"] in existing_ids:
            print(f"  [skip] #{issue['number']} -- already imported (duplicate id)")
            continue
        print(f"  [+] #{issue['number']} {event.author} — {event.book_title} ({event.date})")
        imported.append((issue, event_dict))

    if not imported:
        print("Nothing new to import.")
        return

    if args.dry_run:
        print(f"\n[dry-run] Would import {len(imported)} event(s); no files changed, no issues closed.")
        return

    all_events = existing + [e for _, e in imported]
    write_events(all_events)
    print(f"\nWrote {len(all_events)} total events -> {EVENTS_JSON}")

    for issue, event_dict in imported:
        comment = (
            f"✅ Danke für den Vorschlag! Diese Lesung wurde in die Liste aufgenommen "
            f"(Termin am {event_dict['date']})."
        )
        subprocess.run(
            ["gh", "issue", "close", str(issue["number"]), "--repo", REPO, "--comment", comment],
            capture_output=True, text=True,
        )
        print(f"  Closed issue #{issue['number']}")

    print(
        "\nDon't forget to commit + push data/events.json and data/events.csv "
        "so the live site picks up the new event(s)."
    )


if __name__ == "__main__":
    main()
