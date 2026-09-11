"""Scraper for S. Fischer Verlage (fischerverlage.de) events.

The listing page only exposes ~20 upcoming events (Algolia InstantSearch,
"Load more" is JS-only and out of scope for a plain-requests scraper) and
doesn't carry clean structured fields anyway. Each event's *detail* page,
however, embeds a clean schema.org/Event JSON-LD block with everything we
need (author via `performer`, ISO datetime, venue, full address) -- so we
scrape the listing only for detail-page URLs, then read JSON-LD from each.
"""
from __future__ import annotations

import json
import time

from bs4 import BeautifulSoup

from .base import Event, clean_text, fetch

LISTING_URL = "https://www.fischerverlage.de/veranstaltung"
PUBLISHER = "S. Fischer Verlage"
REQUEST_DELAY_SECONDS = 0.4


def _detail_urls() -> list[str]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")
    urls = []
    for a in soup.select("div.event__links a[href]"):
        href = a["href"]
        if href.startswith("/"):
            href = "https://www.fischerverlage.de" + href
        if href not in urls:
            urls.append(href)
    return urls


def _parse_detail(url: str) -> Event | None:
    try:
        resp = fetch(url)
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "lxml")

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if item.get("@type") != "Event":
                continue

            title = clean_text(item.get("name"))
            start = item.get("startDate") or ""
            date_part = start[:10] if len(start) >= 10 else None
            time_part = start[11:16] if len(start) >= 16 else None

            location = item.get("location") or {}
            venue = clean_text(location.get("name"))
            addr = location.get("address") or {}
            street = clean_text(addr.get("streetAddress"))
            postal = clean_text(addr.get("postalCode"))
            city = clean_text(addr.get("addressLocality"))
            address = ", ".join(p for p in (street, " ".join(filter(None, [postal, city]))) if p) or None

            performers = item.get("performer") or []
            if isinstance(performers, dict):
                performers = [performers]
            author = clean_text(performers[0].get("name")) if performers else None

            organizer_url = ((item.get("organizer") or {}).get("url")) or None
            offer_url = None
            offers = item.get("offers") or []
            if isinstance(offers, dict):
                offers = [offers]
            for offer in offers:
                if offer.get("url"):
                    offer_url = offer["url"]
                    break

            return Event(
                publisher=PUBLISHER,
                author=author,
                title=title,
                date=date_part,
                time=time_part,
                venue=venue,
                city=city,
                address=address,
                url=organizer_url or offer_url or url,
                source_url=url,
                raw_text=start,
                cover_image=item.get("image") or None,
            )
    return None


def scrape() -> list[Event]:
    events: list[Event] = []
    for url in _detail_urls():
        event = _parse_detail(url)
        if event:
            events.append(event)
        time.sleep(REQUEST_DELAY_SECONDS)
    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
