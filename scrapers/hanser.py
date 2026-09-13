"""Scraper for Carl Hanser Verlag / Hanser Literaturverlage (hanser-literaturverlage.de) events.

The public events page is Next.js SSR and caps at 20 items with ?page
ignored server-side, but its own frontend calls a real JSON REST API for
pagination/filtering (found in a shipped JS chunk) which we call directly:
POST /api/events with a facet filter for city == Berlin.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .base import Event, clean_text

API_URL = "https://www.hanser-literaturverlage.de/api/events"
LISTING_URL = "https://www.hanser-literaturverlage.de/veranstaltungen-c-34"
PUBLISHER = "Carl Hanser Verlag"
BERLIN_TZ = ZoneInfo("Europe/Berlin")
PER_PAGE = 100


def _body(page: int) -> dict:
    return {
        "initialFilters": [
            {"facetField": f, "selectedValues": []}
            for f in (
                "event_id_i", "category_ids_ss", "person_ids_ss",
                "publisher_ids_ss", "keywords_ids_ss", "title_ids_ss",
            )
        ],
        "page": page,
        "perPage": PER_PAGE,
        "sort": "date_time_dt ASC,new_time_from_dt ASC",
        "searchValue": "",
        "searchValueTitle": "",
        "facets": [
            {"facetField": "facet_month_year_ids_ss", "selectedValues": []},
            {"facetField": "facet_event_search_city_ss", "selectedValues": ["Berlin"]},
            {"facetField": "facet_todays_date_ss", "selectedValues": []},
            {"facetField": "facet_country_search_ss", "selectedValues": []},
            {"facetField": "facet_next_week_ids_ss", "selectedValues": []},
            {"facetField": "facet_person_ss", "selectedValues": []},
            {"facetField": "facet_title_ss", "selectedValues": []},
        ],
    }


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return clean_text(BeautifulSoup(text, "html.parser").get_text(separator=" "))


def _doc_to_event(doc: dict) -> Event:
    dates = doc.get("dateFrom") or []
    date_iso = dates[0] if dates else None

    time_str = None
    time_raw = doc.get("newTimeFrom")
    if time_raw:
        try:
            # "2000-01-01T19:30:00Z" -- only the time-of-day is meaningful
            dt = datetime.strptime(time_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=ZoneInfo("UTC"))
            time_str = dt.astimezone(BERLIN_TZ).strftime("%H:%M")
        except ValueError:
            pass

    authors = doc.get("author") or []
    author = ", ".join(clean_text(a.get("fullname")) for a in authors if a.get("fullname")) or None
    if not author:
        author = clean_text(doc.get("eventPersonTxt"))

    plz_ids = doc.get("plzIds") or []
    postal = clean_text(plz_ids[0]) if plz_ids else None
    street = clean_text(doc.get("street"))
    city = clean_text(doc.get("city"))
    address = ", ".join(p for p in (street, " ".join(filter(None, [postal, city]))) if p) or None

    books = doc.get("titleBooks") or []
    url = doc.get("link") or doc.get("linkVenue")
    if not url and books and books[0].get("link"):
        book_link = books[0]["link"]
        url = f"https://www.hanser-literaturverlage.de{book_link}" if book_link.startswith("/") else book_link

    cover = credit = None
    if books:
        cover = books[0].get("image")
        # Speculative: this internal search-index API isn't publicly
        # documented, so these are a guess at plausible credit key names
        # rather than something confirmed present -- harmless no-op (stays
        # None) if absent.
        credit = clean_text(books[0].get("imageCredit") or books[0].get("credit"))
    if not cover and authors:
        cover = authors[0].get("image")
        credit = credit or clean_text(authors[0].get("imageCredit") or authors[0].get("credit"))

    book_title = clean_text(books[0].get("fullname")) if books else None

    return Event(
        publisher=PUBLISHER,
        author=author,
        title=_strip_html(doc.get("theme")),
        date=date_iso,
        time=time_str,
        venue=clean_text(doc.get("venue")),
        city=city,
        address=address,
        url=url,
        source_url=LISTING_URL,
        raw_text=clean_text(doc.get("categoryTxt")),
        cover_image=cover,
        image_credit=credit,
        book_title=book_title,
    )


def scrape() -> list[Event]:
    events: list[Event] = []
    page = 1
    while True:
        resp = requests.post(API_URL, json=_body(page), headers={"Content-Type": "application/json"}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        docs = data.get("docs") or []
        events.extend(_doc_to_event(d) for d in docs)

        num_found = data.get("numFound", 0)
        if page * PER_PAGE >= num_found or not docs:
            break
        page += 1

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
