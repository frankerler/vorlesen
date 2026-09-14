#!/usr/bin/env python3
"""Scrape all enabled sites (see sources.json) and write Berlin reading events to disk.

Usage:
    python run.py                  # scrape everything enabled in sources.json
    python run.py --publisher rowohlt hanser   # only run specific scrapers, ignoring sources.json
    python run.py --all-cities     # don't filter to Berlin, keep every city
    python run.py --format csv     # also/instead write data/events.csv

Each scraper module in scrapers/ exposes scrape() -> list[Event] with the
*raw* events it found (any city). This script merges them, filters for
Berlin (unless --all-cities), de-duplicates, sorts by date, and persists
the result as JSON (and optionally CSV).

Which scrapers actually run is controlled by sources.json at the repo root
(edited by hand, or through web/admin.html) -- each entry there needs a
matching scrapers/<id>.py module (see SCRAPERS below) to actually do
anything; sources.json only toggles it on/off, it can't invent a scraper
for a brand new site on its own.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import importlib
import json
import sys
import traceback
from datetime import date
from pathlib import Path

from scrapers.base import Event, authors_overlap, is_berlin, venues_match

DATA_DIR = Path(__file__).parent / "data"
SOURCES_CONFIG_PATH = Path(__file__).parent / "sources.json"

# Registry of *implemented* scrapers: module name -> human label. This is the
# ground truth for what CAN run; sources.json (see load_enabled_sources)
# controls what actually DOES run on a given invocation.
SCRAPERS = {
    # Publishers
    "suhrkamp": "Suhrkamp Verlag",
    "hanser": "Carl Hanser Verlag",
    "rowohlt": "Rowohlt Verlag",
    "fischer": "S. Fischer Verlage",
    "piper": "Piper Verlag",
    "dtv": "dtv Verlag",
    "kiwi": "Kiepenheuer & Witsch",
    "ullstein": "Ullstein Verlag",
    # Venues (host readings for many different publishers' authors --
    # frequently overlap with the publisher scrapes above; see merge_cross_source_duplicates)
    "lcb": "Literarisches Colloquium Berlin",
    "literaturhaus": "Literaturhaus Berlin",
    "lettretage": "Lettrétage",
    "kulturkaufhaus": "Dussmann das KulturKaufhaus",
    "buchbox": "Buchbox! Berlin",
    "proqm": "Pro qm",
    "moritzplatz": "Buchhandlung Moritzplatz",
    "rosalux": "Rosa-Luxemburg-Stiftung",
    "boell": "Heinrich-Böll-Stiftung",
    "zfl": "Leibniz-Zentrum für Literatur- und Kulturforschung (ZfL)",
    "urania": "Urania Berlin",
    "publix": "Publix",
    "taz": "taz",
}


def load_enabled_sources() -> list[str]:
    """Reads sources.json for the list of enabled + implemented scraper ids.

    Falls back to every scraper in SCRAPERS if sources.json is missing or
    unreadable, so a fresh checkout without that file still works.
    """
    if not SOURCES_CONFIG_PATH.exists():
        return list(SCRAPERS)
    try:
        config = json.loads(SOURCES_CONFIG_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print(f"Warning: couldn't read {SOURCES_CONFIG_PATH} ({exc}); running all scrapers.", file=sys.stderr)
        return list(SCRAPERS)

    enabled = [
        s["id"] for s in config.get("sources", [])
        if s.get("enabled") and s.get("implemented", True) and s.get("id") in SCRAPERS
    ]
    return enabled or list(SCRAPERS)


def run_scraper(name: str) -> list[Event]:
    try:
        module = importlib.import_module(f"scrapers.{name}")
    except ModuleNotFoundError:
        print(f"  [skip] scrapers/{name}.py not implemented yet", file=sys.stderr)
        return []
    try:
        events = module.scrape()
        print(f"  [ok]   {name}: {len(events)} events found")
        return events
    except Exception as exc:  # noqa: BLE001 - one bad publisher shouldn't kill the run
        print(f"  [FAIL] {name}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return []


def dedupe(events: list[Event]) -> list[Event]:
    """Exact dedupe within a single source (same publisher/venue, same event id)."""
    seen = {}
    for e in events:
        seen[e.id()] = e  # last write wins; scrapers run in a stable order so this is fine
    return list(seen.values())


def _completeness_score(e: Event) -> tuple:
    """Higher is "more complete" -- used to pick which duplicate record to keep."""
    return (
        bool(e.cover_image),
        bool(e.image_credit),
        bool(e.address),
        bool(e.time),
        bool(e.url),
        len(e.title or ""),
    )


def merge_cross_source_duplicates(events: list[Event]) -> list[Event]:
    """Collapses events that are the same real-world reading reported by two
    different sources (e.g. a Suhrkamp author's event at LCB shows up in both
    Suhrkamp's own scrape and LCB's venue scrape). Different sources rarely
    agree on exact spelling, so this can't be an exact-string dedupe like
    `dedupe()` -- instead, events on the same date whose venue and author
    both fuzzy-match (see scrapers/base.py) are treated as one event, and the
    more complete record (real cover image, address, etc.) is kept.
    """
    by_date: dict = {}
    for e in events:
        by_date.setdefault(e.date, []).append(e)

    kept: list[Event] = []
    for date_key, day_events in by_date.items():
        merged: list[Event] = []
        for e in day_events:
            match_idx = None
            if date_key is not None:  # don't fuzzy-merge events with an unknown date
                for i, existing in enumerate(merged):
                    if venues_match(e.venue, existing.venue) and authors_overlap(e.author, existing.author):
                        match_idx = i
                        break
            if match_idx is None:
                merged.append(e)
            else:
                # Keep whichever of the two records is more complete.
                if _completeness_score(e) > _completeness_score(merged[match_idx]):
                    merged[match_idx] = e
        kept.extend(merged)
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--publisher", nargs="*", choices=list(SCRAPERS), help="Only run these scrapers, ignoring sources.json (default: whatever's enabled there)")
    parser.add_argument("--all-cities", action="store_true", help="Keep events from all cities, not just Berlin")
    parser.add_argument("--include-past", action="store_true", help="Keep events dated before today (default: dropped)")
    parser.add_argument("--format", choices=["json", "csv", "both"], default="json")
    args = parser.parse_args()

    targets = args.publisher or load_enabled_sources()

    print(f"Running {len(targets)} scraper(s): {', '.join(targets)}")
    all_events: list[Event] = []
    for name in targets:
        all_events.extend(run_scraper(name))

    if not args.all_cities:
        before = len(all_events)
        all_events = [e for e in all_events if is_berlin(e.city, e.venue, e.address, e.raw_text)]
        print(f"Filtered to Berlin: {len(all_events)}/{before} events")

    if not args.include_past:
        # Some sources (Rowohlt's sitemap in particular) leave old event
        # pages up long after the date has passed. This is an events-you-
        # can-still-attend app, not an archive, so drop anything dated
        # before today -- keep events with an unparseable/missing date
        # rather than risk silently losing a real upcoming one.
        before = len(all_events)
        today_iso = date.today().isoformat()
        all_events = [e for e in all_events if not e.date or e.date >= today_iso]
        if len(all_events) != before:
            print(f"Filtered out past-dated events: {len(all_events)}/{before} remain")

    all_events = dedupe(all_events)

    before_merge = len(all_events)
    all_events = merge_cross_source_duplicates(all_events)
    if before_merge != len(all_events):
        print(f"Merged cross-source duplicates: {before_merge} -> {len(all_events)} events")

    all_events.sort(key=lambda e: (e.date or "9999-99-99", e.author or ""))

    DATA_DIR.mkdir(exist_ok=True)

    if args.format in ("json", "both"):
        out_path = DATA_DIR / "events.json"
        out_path.write_text(
            json.dumps([e.to_dict() for e in all_events], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote {len(all_events)} events -> {out_path}")

    if args.format in ("csv", "both"):
        out_path = DATA_DIR / "events.csv"
        fieldnames = [f.name for f in dataclasses.fields(Event)] + ["id"]
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for e in all_events:
                writer.writerow(e.to_dict())
        print(f"Wrote {len(all_events)} events -> {out_path}")


if __name__ == "__main__":
    main()
