#!/usr/bin/env python3
"""Fold newsletter signups into data/subscribers.json.

Workflow this script is part of:
1. A visitor uses the newsletter button (top left) on the site to submit
   their email address. It POSTs directly to Formspree (web/app.js) -- the
   same form/endpoint the reading-suggestion form uses, distinguished by a
   hidden "_subject" field ("Newsletter-Anmeldung"), since most Formspree
   plans only allow one form. No account needed for the visitor, no
   secrets exposed client-side.
2. You review submissions in your Formspree dashboard (or the notification
   emails) -- see web/admin.html for the exact steps.
3. Export the submissions you want to keep as CSV from Formspree (Form ->
   Submissions -> Export), then run this script against that file. Rows you
   don't want can just be deleted from the CSV before running it -- there's
   no separate "approve" step, the CSV *is* the approval.

Usage:
    .venv/bin/python scripts/import_newsletter_subscribers.py submissions.csv            # import
    .venv/bin/python scripts/import_newsletter_subscribers.py submissions.csv --dry-run  # preview only
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SUBSCRIBERS_JSON = DATA_DIR / "subscribers.json"

# Formspree exports one column per form field, plus its own metadata columns
# (submission id, timestamp, etc.). Column names vary a bit by account/export
# settings, so matching is case-insensitive and tolerant of a "field:" prefix
# (e.g. some accounts export "field:email") and of a couple of common names
# for the submission timestamp.
EMAIL_COLUMN_NAMES = ["email"]
TIMESTAMP_COLUMN_NAMES = ["created_at", "submitted_at", "date", "timestamp"]


def _find_column(fieldnames: list[str], wanted_names: list[str]) -> str | None:
    for wanted in wanted_names:
        for actual in fieldnames or []:
            cleaned = actual.strip().lower().split(":")[-1]  # tolerate "field:email" style
            if cleaned == wanted:
                return actual
    return None


def load_existing() -> list[dict]:
    if not SUBSCRIBERS_JSON.exists():
        return []
    return json.loads(SUBSCRIBERS_JSON.read_text(encoding="utf-8"))


def write_subscribers(subscribers: list[dict]) -> None:
    subscribers = sorted(subscribers, key=lambda s: s.get("subscribed_at") or "")
    SUBSCRIBERS_JSON.write_text(json.dumps(subscribers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        email_col = _find_column(reader.fieldnames, EMAIL_COLUMN_NAMES)
        if not email_col:
            print(
                f"Couldn't find an 'email' column in {csv_path}. Found columns: {reader.fieldnames}",
                file=sys.stderr,
            )
            sys.exit(1)
        timestamp_col = _find_column(reader.fieldnames, TIMESTAMP_COLUMN_NAMES)

        rows = list(reader)

    existing = load_existing()
    existing_emails = {s["email"].strip().lower() for s in existing if s.get("email")}

    imported = []
    for row in rows:
        email = (row.get(email_col) or "").strip()
        if not email:
            print(f"  [skip] row missing email: {row}")
            continue
        if email.lower() in existing_emails:
            print(f"  [skip] {email} -- already subscribed")
            continue
        subscribed_at = (row.get(timestamp_col) or "").strip() if timestamp_col else ""
        print(f"  [+] {email}" + (f" ({subscribed_at})" if subscribed_at else ""))
        imported.append({"email": email, "subscribed_at": subscribed_at or None})
        existing_emails.add(email.lower())  # guard against duplicate rows within the same CSV

    if not imported:
        print("Nothing new to import.")
        return

    if args.dry_run:
        print(f"\n[dry-run] Would import {len(imported)} subscriber(s); no files changed.")
        return

    all_subscribers = existing + imported
    write_subscribers(all_subscribers)
    print(f"\nWrote {len(all_subscribers)} total subscriber(s) -> {SUBSCRIBERS_JSON}")
    print("Now commit + push data/subscribers.json so the admin page picks it up.")


if __name__ == "__main__":
    main()
