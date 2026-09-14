"""Scraper for the Heinrich-Böll-Stiftung's event calendar (calendar.boell.de).

This is a separate Drupal site from boell.de itself, aggregating events
from the Bundesstiftung Berlin, regional Bildungswerke, and international
offices -- we use its own city facet (?f[0]=ort_slide_in:2445) to get only
Berlin-located ones (this covers both the Bundesstiftung and Bildungswerk
Berlin). Like Urania/Publix/taz, category labels here don't cleanly
separate book events from the foundation's many discussions/workshops, so
we keep only entries that look literary by keyword.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://calendar.boell.de/de/calendar/frontpage?f[0]=ort_slide_in:2445"
BASE_URL = "https://calendar.boell.de"
PUBLISHER = "Heinrich-Böll-Stiftung"
DEFAULT_ADDRESS = "Schumannstr. 8, 10117 Berlin"
MAX_PAGES = 10

LITERARY_KEYWORDS = ("lesung", "buch", "roman", "gedichte", "literatur", "liest", "buchklub", "buchvorstellung")
_PLACEHOLDER_ADDRESS_RE = re.compile(r"siehe\s+veranstaltungsbeschreibung", re.IGNORECASE)


def _is_literary(*texts: str | None) -> bool:
    combined = " ".join(t for t in texts if t).lower()
    return any(kw in combined for kw in LITERARY_KEYWORDS)


def _parse_detail(url: str) -> dict:
    out: dict = {}
    try:
        resp = fetch(url)
    except Exception:
        return out
    soup = BeautifulSoup(resp.text, "lxml")

    start_meta = soup.select_one('meta[name="datetime-start"]')
    if start_meta and start_meta.get("content"):
        content = start_meta["content"]
        if len(content) >= 10:
            out["date"] = content[:10]
        if len(content) >= 16:
            out["time"] = content[11:16]

    address_el = soup.select_one("dl.field--location address")
    if address_el:
        text = clean_text(address_el.get_text(" "))
        if text and not _PLACEHOLDER_ADDRESS_RE.search(text):
            parts = [p.strip() for p in text.split(",")]
            out["address"] = text
            if parts:
                out["venue"] = parts[0]
            if "berlin" in text.lower():
                out["city"] = "Berlin"

    organizer_el = soup.select_one("dl.field--organizer dd")
    if organizer_el and "venue" not in out:
        organizer = clean_text(organizer_el.get_text())
        if organizer:
            out["venue"] = organizer

    body_el = soup.select_one("div.field--name-body")
    if body_el:
        out["description"] = clean_text(body_el.get_text(" "))

    return out


def scrape() -> list[Event]:
    events: list[Event] = []
    seen_ids: set[str] = set()

    for page in range(MAX_PAGES):
        url = f"{LISTING_URL}&page={page}"
        resp = fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("div.views-row.event-view")
        if not rows:
            break

        new_rows = 0
        for row in rows:
            wrapper = row.select_one("div.eventlist-white-wrapper[data-history-node-id]")
            node_id = wrapper.get("data-history-node-id") if wrapper else None
            if node_id:
                if node_id in seen_ids:
                    continue
                seen_ids.add(node_id)
            new_rows += 1

            link = row.select_one("div.event--title--wrapper a[href]")
            title_el = row.select_one("h2.event--title")
            title = clean_text(title_el.get_text()) if title_el else None
            subtitle_el = row.select_one("div.field--subtitle")
            subtitle = clean_text(subtitle_el.get_text()) if subtitle_el else None
            category_el = row.select_one("span.field--event_type")
            category = clean_text(category_el.get_text()) if category_el else None

            if not _is_literary(title, subtitle, category):
                continue
            if not link or not link.get("href"):
                continue

            href = link["href"]
            event_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            details = _parse_detail(event_url)

            events.append(
                Event(
                    publisher=PUBLISHER,
                    author=None,
                    title=title,
                    date=details.get("date"),
                    time=details.get("time"),
                    venue=details.get("venue") or PUBLISHER,
                    city=details.get("city") or "Berlin",
                    address=details.get("address") or DEFAULT_ADDRESS,
                    url=event_url,
                    source_url=LISTING_URL,
                    raw_text=details.get("description") or subtitle,
                    book_title=extract_quoted_title(title, subtitle, details.get("description")),
                )
            )

        if new_rows == 0:
            break

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
