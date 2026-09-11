"""Scraper for Ullstein Verlag (ullstein.de) events.

Next.js SSR page that embeds the full Algolia result set as clean JSON in
a <script id="__NEXT_DATA__"> tag -- no HTML/CSS-class parsing needed.
Paginates via ?page=N (24 hits/page); no server-side city filter, so we
fetch every page and filter for Berlin in run.py / here.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, fetch

LISTING_URL = "https://www.ullstein.de/veranstaltungen"
PUBLISHER = "Ullstein Verlag"
MAX_PAGES = 30  # safety cap; site had 9 pages / 212 events at research time


def _page_hits(page: int) -> list[dict]:
    url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
    resp = fetch(url)
    soup = BeautifulSoup(resp.text, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []
    try:
        data = json.loads(script.string)
    except ValueError:
        return []

    try:
        initial_results = data["props"]["pageProps"]["serverState"]["initialResults"]
    except (KeyError, TypeError):
        return []

    for index_name, payload in initial_results.items():
        if "events" not in index_name:
            continue
        results = payload.get("results") or []
        if results and isinstance(results, list):
            return results[0].get("hits", [])
    return []


def _hit_to_event(hit: dict) -> Event:
    authors = hit.get("authorNames") or []
    author = clean_text(authors[0]) if authors else None

    date_str = hit.get("date")  # "DD.MM.YYYY"
    iso_date = None
    if date_str:
        m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
        if m:
            d, mo, y = m.groups()
            iso_date = f"{y}-{int(mo):02d}-{int(d):02d}"

    zip_code = hit.get("zip")
    city = hit.get("city")
    street = hit.get("streetAddress")
    address = ", ".join(p for p in (street, " ".join(filter(None, [zip_code, city]))) if p) or None

    uri = hit.get("uri") or ""
    url = f"https://www.ullstein.de{uri}" if uri.startswith("/") else (uri or None)

    cover = (hit.get("cover") or {}).get("full")
    book_titles = hit.get("productTitels") or []
    book_title = clean_text(book_titles[0]) if book_titles else None

    return Event(
        publisher=PUBLISHER,
        author=author,
        title=clean_text(hit.get("title")),
        date=iso_date,
        time=clean_text(hit.get("time")),
        venue=clean_text(hit.get("locality")),
        city=clean_text(city),
        address=address,
        url=url,
        source_url=LISTING_URL,
        raw_text=f"{date_str} {hit.get('time') or ''}".strip(),
        cover_image=cover,
        book_title=book_title,
    )


def scrape() -> list[Event]:
    events: list[Event] = []
    for page in range(1, MAX_PAGES + 1):
        hits = _page_hits(page)
        if not hits:
            break
        events.extend(_hit_to_event(h) for h in hits)
    return events


if __name__ == "__main__":
    for e in scrape():
        if e.city and e.city.lower() == "berlin":
            print(e.to_dict())
