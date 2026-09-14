"""Scraper for the Leibniz-Zentrum für Literatur- und Kulturforschung (ZfL
Berlin, zfl-berlin.org) -- what the user meant by "Leibnitz Center": of the
Berlin institutions with "Leibniz" in the name, this is the one that's
literature/culture-focused and hosts its own public readings/talks (the
"Leibniz-Saal" is just a room inside the BBAW, not an independent host with
its own events page).

The listing page is paginated, but every page also embeds a `kaldata`
JS array (feeding a calendar widget) with ALL upcoming events in one blob
-- much simpler than paginating. ZfL's event mix includes academic
conferences/workshops alongside readings/book presentations; we keep only
the latter via the `zuordnung`/`art` category fields.
"""
from __future__ import annotations

import html
import json
import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://www.zfl-berlin.org/zfl-events.html"
BASE_URL = "https://www.zfl-berlin.org"
PUBLISHER = "Leibniz-Zentrum für Literatur- und Kulturforschung (ZfL)"
DEFAULT_ADDRESS = "Pariser Str. 1, 10719 Berlin"

_KALDATA_RE = re.compile(r"var\s+kaldata\s*=\s*(\[.*?\]);", re.DOTALL)

LITERARY_CATEGORIES = ("reading", "book presentation", "lesung", "buchpräsentation", "buchvorstellung")


def _is_literary(entry: dict) -> bool:
    combined = f"{entry.get('art', '')} {entry.get('zuordnung', '')}".lower()
    return any(kw in combined for kw in LITERARY_CATEGORIES)


def _parse_detail(url: str) -> dict:
    """Best-effort extraction of venue/address/speakers from the detail page."""
    out: dict = {}
    try:
        resp = fetch(url)
    except Exception:
        return out
    soup = BeautifulSoup(resp.text, "lxml")

    ort_el = soup.select_one("div.veranstaltung_ort")
    if ort_el:
        text = clean_text(ort_el.get_text(" "))
        if text:
            out["address"] = re.sub(r"^Venue:\s*", "", text, flags=re.IGNORECASE)

    organized_el = soup.select_one("div.veranstaltung_organisiert")
    if organized_el:
        text = clean_text(organized_el.get_text(" "))
        if text:
            out["speakers"] = re.sub(r"^Organized by\s*", "", text, flags=re.IGNORECASE)

    text_el = soup.select_one("div.veranstaltung_text")
    if text_el:
        out["description"] = clean_text(text_el.get_text(" "))

    return out


def scrape() -> list[Event]:
    resp = fetch(LISTING_URL)
    m = _KALDATA_RE.search(resp.text)
    if not m:
        return []

    try:
        entries = json.loads(html.unescape(m.group(1)))
    except ValueError:
        return []

    events: list[Event] = []
    for entry in entries:
        if not _is_literary(entry):
            continue

        title = clean_text(html.unescape(entry.get("titel") or ""))
        date_part = entry.get("datum") or None
        time_raw = clean_text(entry.get("zeit"))
        time_part = None
        if time_raw:
            tm = re.search(r"(\d{1,2})[.:](\d{2})\s*(am|pm)?", time_raw, re.IGNORECASE)
            if tm:
                hour, minute, meridiem = tm.groups()
                hour_int = int(hour)
                if meridiem and meridiem.lower() == "pm" and hour_int != 12:
                    hour_int += 12
                elif meridiem and meridiem.lower() == "am" and hour_int == 12:
                    hour_int = 0
                time_part = f"{hour_int:02d}:{minute}"

        rel_url = entry.get("url") or ""
        url = rel_url if rel_url.startswith("http") else f"{BASE_URL}{rel_url}"

        details = _parse_detail(url) if rel_url else {}

        author = details.get("speakers")
        description = details.get("description")
        address = details.get("address") or DEFAULT_ADDRESS

        events.append(
            Event(
                publisher=PUBLISHER,
                author=author,
                title=title,
                date=date_part,
                time=time_part,
                venue=PUBLISHER,
                city="Berlin",
                address=address,
                url=url or LISTING_URL,
                source_url=LISTING_URL,
                raw_text=description or clean_text(entry.get("art")),
                book_title=extract_quoted_title(title, description),
            )
        )

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
