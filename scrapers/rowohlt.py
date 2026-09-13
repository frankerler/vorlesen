"""Scraper for Rowohlt Verlag (rowohlt.de) events.

The public listing page only renders 20 events (Algolia InstantSearch,
"Mehr laden" is JS-only) and has no working server-side city filter.
Instead we use the site's own events sitemap, which lists every current
event detail-page URL, then read each detail page's schema.org/Event
JSON-LD block for clean structured data.

Detail-page slugs already encode the city (e.g.
".../lesung-waslat-hasrat-nazimi-berlin-19715-260911"), so we pre-filter
the sitemap for "-berlin-" before fetching detail pages -- avoids ~450
unnecessary requests -- then double-check the real city from JSON-LD.
"""
from __future__ import annotations

import json
import re
import time

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch, image_from_schema_org

SITEMAP_URL = "https://www.rowohlt.de/sitemap-events.xml"
LISTING_URL = "https://www.rowohlt.de/veranstaltung"
PUBLISHER = "Rowohlt Verlag"
REQUEST_DELAY_SECONDS = 0.3


def _sitemap_urls() -> list[str]:
    resp = fetch(SITEMAP_URL)
    soup = BeautifulSoup(resp.text, "xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc")]


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
            author = clean_text(performers[0].get("name")) if performers else title

            offers = item.get("offers") or []
            if isinstance(offers, dict):
                offers = [offers]
            offer_url = next((o.get("url") for o in offers if o.get("url")), None)
            organizer_url = (item.get("organizer") or {}).get("url") or None

            type_el = soup.select_one("strong.event-intro__main__type")
            event_type = clean_text(type_el.get_text()) if type_el else None

            # No dedicated book-title field here; best-effort extraction from
            # the free-text description (title itself is usually just the
            # author's name, e.g. "Waslat Hasrat-Nazimi").
            book_title = extract_quoted_title(item.get("description"))
            cover, credit = image_from_schema_org(item.get("image"))

            return Event(
                publisher=PUBLISHER,
                author=author,
                title=title,
                date=date_part,
                time=time_part,
                venue=venue,
                city=city,
                address=address,
                url=offer_url or organizer_url or url,
                source_url=url,
                # event_type ("Lesung"/"Premiere"/...) is too short to be a
                # useful description on its own; the free-text blurb is much
                # more informative for the detail view.
                raw_text=clean_text(item.get("description")) or event_type,
                cover_image=cover,
                image_credit=credit,
                book_title=book_title,
            )
    return None


def scrape() -> list[Event]:
    urls = _sitemap_urls()
    # Slugs encode city as "...-<city>-<id>-<yymmdd>"; pre-filter to skip
    # obviously-non-Berlin events without a full detail-page fetch.
    candidate_urls = [u for u in urls if re.search(r"-berlin-\d+-\d{6}", u, re.IGNORECASE)]

    events: list[Event] = []
    for url in candidate_urls:
        event = _parse_detail(url)
        if event and event.city and event.city.lower() == "berlin":
            events.append(event)
        time.sleep(REQUEST_DELAY_SECONDS)
    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
