"""Scraper for Urania Berlin (urania.de) events.

Urania hosts a broad mix of event types (science talks, panel discussions,
concerts, book readings, ...) with no clean category filter for "just the
literary ones" -- so this scraper keeps everything from the listing but
flags literary/book events via a keyword heuristic on the title/format/
series text, and run.py-level consumers can rely on `raw_text`/`title`
containing those same signals. We keep only the ones that look literary
here, since including e.g. science-panel events would dilute a books app.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://www.urania.de/kalender/"
PUBLISHER = "Urania Berlin"
VENUE_ADDRESS = "An der Urania 17, 10787 Berlin"

_DAY_ATTR_RE = re.compile(r"^(\d{1,2})-[a-zäöü]+-(\d{1,2})-(\d{4})$", re.IGNORECASE)
_TIME_RE = re.compile(r"(\d{1,2}:\d{2})")

LITERARY_KEYWORDS = (
    "lesung", "buchpremiere", "buchpreis", "buchvorstellung", "buchpräsentation",
    "liest", "literatur", "poesie", "roman", "gedichte", "schriftsteller",
)


def _is_literary(*texts: str | None) -> bool:
    combined = " ".join(t for t in texts if t).lower()
    return any(kw in combined for kw in LITERARY_KEYWORDS)


def scrape() -> list[Event]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    events: list[Event] = []
    for day_el in soup.select("div.c-event-calendar_day[data-day]"):
        m = _DAY_ATTR_RE.match(day_el["data-day"].strip())
        date_part = None
        if m:
            day, month, year = m.groups()
            date_part = f"{year}-{int(month):02d}-{int(day):02d}"

        for item in day_el.select("div.c-event-calendar-item"):
            link = item.select_one("a.c-event-calendar-item_content")
            if not link:
                continue

            series_el = link.select_one("h5")
            title_el = link.select_one("h3")
            format_el = link.select_one("h6")
            speaker_el = link.select_one(".c-event-calendar-item_content_text strong")

            series = clean_text(series_el.get_text()) if series_el else None
            title = clean_text(title_el.get_text()) if title_el else None
            event_format = clean_text(format_el.get_text()) if format_el else None
            author = clean_text(speaker_el.get_text()) if speaker_el else None

            if not _is_literary(title, event_format, series):
                continue

            time_el = item.select_one(".c-event-calendar-item_time")
            time_part = None
            if time_el:
                tm = _TIME_RE.search(time_el.get_text())
                if tm:
                    time_part = tm.group(1)

            url = link.get("href") or LISTING_URL

            events.append(
                Event(
                    publisher=PUBLISHER,
                    author=author,
                    title=title,
                    date=date_part,
                    time=time_part,
                    venue=PUBLISHER,
                    city="Berlin",
                    address=VENUE_ADDRESS,
                    url=url,
                    source_url=LISTING_URL,
                    raw_text=event_format,
                    book_title=extract_quoted_title(title),
                )
            )

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
