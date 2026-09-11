"""Scraper for Kiepenheuer & Witsch (kiwi-verlag.de) events.

The rendered HTML page only ever contains the first 20 events (Algolia
InstantSearch, client-side "load more"), with no street address and no
working server-side city filter.

Instead we call the same Algolia index the page's own JS widget uses
directly: a public *search-only* API key is embedded in KiWi's shipped
`algolia.*.js` bundle (meant for exactly this kind of client-side query --
it's read-only and cannot write/delete anything). Querying it directly
gives clean JSON with the full address and a true server-side city filter,
instead of scraping HTML capped at 20 results.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .base import Event, clean_text
import requests

ALGOLIA_APP_ID = "II1TGVJXDC"
ALGOLIA_SEARCH_KEY = "67f327b4b55d48042cd2c71e5a53ffc3"  # public search-only key, shipped client-side
ALGOLIA_INDEX = "prod_kiwi_event_start_date_asc"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"

PUBLISHER = "Kiepenheuer & Witsch"
LISTING_URL = "https://www.kiwi-verlag.de/veranstaltung"
BERLIN_TZ = ZoneInfo("Europe/Berlin")
HITS_PER_PAGE = 100


def _query(page: int) -> dict:
    headers = {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": ALGOLIA_SEARCH_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "query": "",
        "filters": 'objectType:event AND events.adressLocality:"Berlin"',
        "hitsPerPage": HITS_PER_PAGE,
        "page": page,
    }
    resp = requests.post(ALGOLIA_URL, headers=headers, json=body, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _hit_events(hit: dict) -> list[Event]:
    out: list[Event] = []
    fallback_title = clean_text(hit.get("title"))

    for ev in hit.get("events") or []:
        if clean_text(ev.get("adressLocality")) != "Berlin":
            continue  # hit can bundle event instances in multiple cities

        contributors = ev.get("relatedContributors") or []
        author = clean_text(contributors[0].get("name")) if contributors else fallback_title

        start_ts = ev.get("startDate")
        date_iso = time_str = None
        if start_ts:
            dt = datetime.fromtimestamp(start_ts, tz=BERLIN_TZ)
            date_iso = dt.date().isoformat()
            if ev.get("hasTime"):
                time_str = dt.strftime("%H:%M")

        street = clean_text(ev.get("streetAddress"))
        postal = clean_text(ev.get("postalCode"))
        city = clean_text(ev.get("adressLocality"))
        address = ", ".join(p for p in (street, " ".join(filter(None, [postal, city]))) if p) or None

        seo_url = ev.get("seoUrl")
        url = f"https://www.kiwi-verlag.de/veranstaltung/{seo_url}" if seo_url else LISTING_URL

        products = ev.get("relatedProducts") or []
        cover = products[0].get("primaryImageLink") if products else None
        if not cover and contributors:
            cover = contributors[0].get("imageLink")

        description = clean_text(BeautifulSoup(hit.get("description") or "", "html.parser").get_text(" "))
        book_title = clean_text(products[0].get("title")) if products else None

        out.append(
            Event(
                publisher=PUBLISHER,
                author=author,
                title=description or fallback_title or ev.get("type"),
                date=date_iso,
                time=time_str,
                venue=clean_text(ev.get("location")),
                city=city,
                address=address,
                url=url,
                source_url=LISTING_URL,
                raw_text=ev.get("type"),
                cover_image=cover,
                book_title=book_title,
            )
        )
    return out


def scrape() -> list[Event]:
    events: list[Event] = []
    page = 0
    while True:
        data = _query(page)
        hits = data.get("hits") or []
        for hit in hits:
            events.extend(_hit_events(hit))
        page += 1
        if page >= data.get("nbPages", 0):
            break
    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
