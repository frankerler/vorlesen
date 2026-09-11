#!/usr/bin/env python3
"""Fold reviewed community-suggested readings into data/events.json.

Workflow this script is part of:
1. A visitor uses the "+" button on the site to submit a reading suggestion.
   It POSTs directly to Formspree (web/app.js) -- no account needed, no
   secrets exposed client-side.
2. You review submissions in your Formspree dashboard (or the notification
   emails). See web/admin.html for the exact steps.
3. Export the submissions you want to keep as CSV from Formspree (Form ->
   Submissions -> Export), then run this script against that file. Rows you
   don't want can just be deleted from the CSV before running it -- there's
   no separate "approve" step, the CSV *is* the approval.

Usage:
    .venv/bin/python scripts/import_formspree_submissions.py submissions.csv            # import
    .venv/bin/python scripts/import_formspree_submissions.py submissions.csv --dry-run  # preview only
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.base import Event  # noqa: E402

DATA_DIR = Path(__file__).parent.parent / "data"
EVENTS_JSON = DATA_DIR / "events.json"
EVENTS_CSV = DATA_DIR / "events.csv"

# Formspree exports one column per form field (see the "name" attributes in
# web/index.html's #suggest-form), plus its own metadata columns (submission
# id, timestamp, etc.) which we simply ignore. Matching is case-insensitive
# and tolerant of Formspree prefixing columns (e.g. some accounts export
# "field:author" style headers).
FIELD_NAMES = ["author", "book_title", "venue", "address", "date", "time", "url", "notes"]


def _normalize_headers(fieldnames: list[str]) -> dict:
    """Maps our expected field name -> the actual CSV column name that matches it."""
    mapping = {}
    for wanted in FIELD_NAMES:
        for actual in fieldnames or []:
            cleaned = actual.strip().lower().split(":")[-1]  # tolerate "field:author" style
            if cleaned == wanted:
                mapping[wanted] = actual
                break
    return mapping


def row_to_event(row: dict, header_map: dict) -> Event | None:
    def get(field: str) -> str | None:
        col = header_map.get(field)
        if not col:
            return None
        value = (row.get(col) or "").strip()
        return value or None

    author = get("author")
    book_title = get("book_title")
    date = get("date")
    if not author or not book_title or not date:
        return None

    return Event(
        publisher="Community-Vorschlag",
        author=author,
        title=book_title,
        date=date,
        time=get("time"),
        venue=get("venue"),
        city="Berlin",
        address=get("address"),
        url=get("url"),
        source_url="https://formspree.io/",
        raw_text=get("notes"),
        book_title=book_title,
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
    parser.add_argument("csv_path", help="Path to a Formspree submissions CSV export")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be imported without writing")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header_map = _normalize_headers(reader.fieldnames)
        missing_required = [f for f in ("author", "book_title", "date") if f not in header_map]
        if missing_required:
            print(
                f"Couldn't find required column(s) {missing_required} in {csv_path}. "
                f"Found columns: {reader.fieldnames}",
                file=sys.stderr,
            )
            sys.exit(1)

        rows = list(reader)

    existing = load_existing_events()
    existing_ids = {e["id"] for e in existing}

    imported = []
    for row in rows:
        event = row_to_event(row, header_map)
        if event is None:
            print(f"  [skip] row missing author/book_title/date: {row}")
            continue
        event_dict = event.to_dict()
        if event_dict["id"] in existing_ids:
            print(f"  [skip] {event.author} — {event.book_title} ({event.date}) -- already imported")
            continue
        print(f"  [+] {event.author} — {event.book_title} ({event.date})")
        imported.append(event_dict)

    if not imported:
        print("Nothing new to import.")
        return

    if args.dry_run:
        print(f"\n[dry-run] Would import {len(imported)} event(s); no files changed.")
        return

    all_events = existing + imported
    write_events(all_events)
    print(f"\nWrote {len(all_events)} total events -> {EVENTS_JSON}")
    print("Now commit + push data/events.json and data/events.csv so the live site picks it up.")


if __name__ == "__main__":
    main()
