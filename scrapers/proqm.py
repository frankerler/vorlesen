"""Scraper for Pro qm (pro-qm.de) events.

All events (future and past) render on one page in a single date-descending
list; future ones are marked with an "date-hence" class, past ones
"date-ago" -- since the list is sorted, everything upcoming appears before
the first "date-ago" item, so no pagination is needed. No JSON-LD anywhere;
venue/address is static (all events happen at the shop itself), hardcoded
rather than scraped per-event.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://pro-qm.de/events"
BASE_URL = "https://pro-qm.de"
PUBLISHER = "Pro qm"
VENUE_ADDRESS = "Almstadtstraße 48-50, 10119 Berlin"
BERLIN_TZ = ZoneInfo("Europe/Berlin")

_AUTHOR_RE = re.compile(r"\b(?:mit|with)\s+(.+)$", re.IGNORECASE)


def _extract_author(subtitle: str | None) -> str | None:
    if not subtitle:
        return None
    m = _AUTHOR_RE.search(subtitle)
    return clean_text(m.group(1)) if m else None


def scrape() -> list[Event]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    events: list[Event] = []
    for li in soup.select("ul.event__list li.event__listitem"):
        if "date-ago" in (li.get("class") or []):
            break  # date-descending list; everything after this is past

        time_el = li.select_one("time[datetime]")
        date_part = time_part = None
        if time_el:
            raw = time_el["datetime"]
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(BERLIN_TZ)
                date_part = dt.date().isoformat()
                time_part = dt.strftime("%H:%M")
            except ValueError:
                pass

        title_link = li.select_one("h2.event__title a")
        title = clean_text(title_link.get_text()) if title_link else None
        href = title_link.get("href") if title_link else None
        url = None
        if href:
            href = href.replace("/index.php/event/", "/event/")
            url = href if href.startswith("http") else f"{BASE_URL}{href}"

        subtitle_el = li.select_one("div.event__subtitle p") or li.select_one("div.event__subtitle")
        subtitle = clean_text(subtitle_el.get_text()) if subtitle_el else None

        events.append(
            Event(
                publisher=PUBLISHER,
                author=_extract_author(subtitle),
                title=title,
                date=date_part,
                time=time_part,
                venue=PUBLISHER,
                city="Berlin",
                address=VENUE_ADDRESS,
                url=url or LISTING_URL,
                source_url=LISTING_URL,
                raw_text=subtitle,
                book_title=extract_quoted_title(title, subtitle),
            )
        )

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
