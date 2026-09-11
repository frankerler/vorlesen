#!/usr/bin/env python3
"""Compare two events.json snapshots and record what's new.

Used by the nightly crawl workflow (.github/workflows/nightly-crawl.yml) to
answer "did last night's crawl find anything new?" -- writes
data/last_run.json, which web/admin.html reads to show a "N new events"
banner.

Usage:
    python scripts/diff_events.py <before.json> <after.json>
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
LAST_RUN_PATH = DATA_DIR / "last_run.json"


def load(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    before = load(sys.argv[1])
    after = load(sys.argv[2])

    before_ids = {e["id"] for e in before}
    new_events = [e for e in after if e["id"] not in before_ids]
    removed_events = [e for e in before if e["id"] not in {e2["id"] for e2 in after}]

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_events": len(after),
        "new_count": len(new_events),
        "removed_count": len(removed_events),
        "new_events": [
            {
                "id": e["id"], "author": e.get("author"), "book_title": e.get("book_title") or e.get("title"),
                "date": e.get("date"), "venue": e.get("venue"), "publisher": e.get("publisher"),
            }
            for e in new_events
        ],
    }

    LAST_RUN_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{summary['new_count']} new, {summary['removed_count']} removed, {summary['total_events']} total -> {LAST_RUN_PATH}")


if __name__ == "__main__":
    main()
