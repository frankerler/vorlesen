"""Scraper for Lettrétage (lettretage.de) -- an independent Berlin literature venue.

This is a *venue* source rather than a publisher: the listing page has no
dedicated "author" field, so we do best-effort extraction from the detail
page's free-text description. The `publisher` field on Event is reused here
to hold the venue name (see scrapers/base.py) -- run.py's cross-source dedup
treats venue-hosted events the same as publisher-hosted ones when matching
on date+venue+author, since the same reading is often listed by both a
book's publisher and the venue that's hosting it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://www.lettretage.de/programm"
VENUE = "Lettrétage"
BASE_URL = "https://www.lettretage.de"
BERLIN_TZ = ZoneInfo("Europe/Berlin")

# Heuristics for pulling an author name out of free-text event descriptions.
# Matches "<First Last> liest", "liest <First Last>", "im Gespräch mit <First Last>".
# Requires at least two capitalized words (first + last name) to avoid false
# positives like "... sogar mit Humor ..." matching a single capitalized noun.
# Deliberately excludes a bare "mit <Name>" pattern -- too noisy on its own
# (matches "mit Spannung", "mit Freude", etc.).
NAME = r"([A-ZÄÖÜ][\wäöüÄÖÜß.\-]+(?:\s+[A-ZÄÖÜ][\wäöüÄÖÜß.\-]+){1,3})"
AUTHOR_PATTERNS = [
    re.compile(rf"{NAME}\s+liest\b"),
    re.compile(rf"\bliest\s+{NAME}"),
    re.compile(rf"im Gespräch mit\s+{NAME}"),
]


def _guess_author(text: str | None) -> str | None:
    """Best-effort author extraction; None (not the title) when no pattern matches --
    the venue's listing often isn't a book reading with a clean single author."""
    if not text:
        return None
    for pattern in AUTHOR_PATTERNS:
        m = pattern.search(text)
        if m:
            return clean_text(m.group(1))
    return None


def _detail_urls() -> list[tuple[str, str]]:
    """Returns [(title, detail_url), ...] from the listing page."""
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")
    out = []
    for item in soup.select("div.collection-item--event"):
        link = item.select_one("a.headline-link")
        if not link or not link.get("href"):
            continue
        href = link["href"]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        title_el = link.select_one("h2.list-teaser-heading") or link
        title = clean_text(title_el.get_text())
        out.append((title, url))
    return out


def _parse_detail(title: str, url: str) -> Event | None:
    try:
        resp = fetch(url)
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "lxml")

    date_part = time_part = venue = address = cover = None
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if item.get("@type") != "Event":
                continue
            start = item.get("startDate") or ""
            if start:
                try:
                    # JSON-LD startDate is UTC ("...Z"); convert to local Berlin time.
                    dt_utc = datetime.strptime(start[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
                    dt_local = dt_utc.astimezone(BERLIN_TZ)
                    date_part = dt_local.date().isoformat()
                    time_part = dt_local.strftime("%H:%M")
                except ValueError:
                    date_part = start[:10] if len(start) >= 10 else None
                    time_part = None

            location = item.get("location") or {}
            addr = location.get("address") or {}
            street = clean_text(addr.get("streetAddress"))
            postal = clean_text(addr.get("postalCode"))
            city = clean_text(addr.get("addressLocality"))
            address = ", ".join(p for p in (street, " ".join(filter(None, [postal, city]))) if p) or None
            venue = VENUE

            cover = item.get("image") or None
            break

    body_el = soup.select_one("div.rich-text-detail-page-1")
    description = clean_text(body_el.get_text(" ")) if body_el else None
    author = _guess_author(description)
    # Best-effort only: many Lettrétage events (workshops, performances) have
    # no single book at all, so this is often None -- that's expected here.
    book_title = extract_quoted_title(title, description)

    return Event(
        publisher=VENUE,
        author=author,
        title=title,
        date=date_part,
        time=time_part,
        venue=venue or VENUE,
        city="Berlin",
        address=address or "Veteranenstr. 21, 10119 Berlin",
        url=url,
        source_url=LISTING_URL,
        raw_text=description,
        cover_image=cover,
        book_title=book_title,
    )


def scrape() -> list[Event]:
    events: list[Event] = []
    for title, url in _detail_urls():
        event = _parse_detail(title, url)
        if event:
            events.append(event)
    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
