"""Scraper for Buchhandlung Moritzplatz (buch-moritzplatz.buchhandlung.de) events.

This shop runs on the "Libri" shared webshop platform used by many German
independent bookshops -- the page itself is a client-rendered SPA (empty
<body>), but the data it hydrates from ships as a JSON blob inline in a
<script> tag (window.LibriInitialWsApiData), so we read that directly
instead of needing a headless browser.

Quirk: the `date` field's time-of-day is not the real event start time --
it's stored as local midnight *expressed in UTC* (e.g. "22:00:00Z" for a
Europe/Berlin date), which happens to convert back to exactly local
midnight once you apply the Berlin timezone -- so converting timezone
alone gives the right calendar date; the real clock time has to be
regexed out of the free-text description instead.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://buch-moritzplatz.buchhandlung.de/shop/magazine/134234/veranstaltungen.html"
BASE_URL = "https://buch-moritzplatz.buchhandlung.de"
MEDIA_BASE = "https://media-all.buchhandlung.de/shared-cms/media/"
PUBLISHER = "Buchhandlung Moritzplatz"
VENUE_ADDRESS = "Prinzenstraße 85, 10969 Berlin"
BERLIN_TZ = ZoneInfo("Europe/Berlin")

_TIME_RE = re.compile(r"\bum\s+(\d{1,2}[:.]\d{2})\s*Uhr", re.IGNORECASE)
_AUTHOR_TITLE_RE = re.compile(r"^(.*?)\s+mit\s+»(.+)«\s*$")


def _extract_json_blob(html: str, marker: str) -> dict | None:
    idx = html.find(marker)
    if idx == -1:
        return None
    start = html.find("{", idx)
    if start == -1:
        return None
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(html, start)
    except ValueError:
        return None
    return data


def _strip_html(html_fragment: str | None) -> str | None:
    if not html_fragment:
        return None
    return clean_text(BeautifulSoup(html_fragment, "html.parser").get_text(" "))


def _image_url(images: dict, key: str | None) -> str | None:
    if not key:
        return None
    entry = images.get(key)
    if not entry:
        return None
    path = entry.get("path")
    return f"{MEDIA_BASE}{path}" if path else None


def scrape() -> list[Event]:
    resp = fetch(LISTING_URL)
    data = _extract_json_blob(resp.text, "window.LibriInitialWsApiData=")
    if not data:
        return []

    shop_page = data.get("shopPage") or {}
    modules = shop_page.get("modules") or []
    images = ((shop_page.get("moduleData") or {}).get("images")) or {}

    events: list[Event] = []
    for module in modules:
        content_raw = module.get("content")
        if not content_raw:
            continue
        try:
            content = json.loads(content_raw)
        except (ValueError, TypeError):
            continue
        attrs = content.get("attributes") or {}

        def attr(name: str):
            return (attrs.get(name) or {}).get("value")

        raw_title = clean_text(attr("title"))
        author = None
        book_title = None
        if raw_title:
            m = _AUTHOR_TITLE_RE.match(raw_title)
            if m:
                author = clean_text(m.group(1))
                book_title = clean_text(m.group(2))
            else:
                book_title = extract_quoted_title(raw_title)

        date_iso = attr("date")
        date_part = None
        if date_iso:
            try:
                dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00")).astimezone(BERLIN_TZ)
                date_part = dt.date().isoformat()
            except ValueError:
                pass

        description_html = attr("description")
        description = _strip_html(description_html)
        time_part = None
        if description:
            m = _TIME_RE.search(description)
            if m:
                time_part = m.group(1).replace(".", ":")

        event_type = clean_text(attr("eventType"))

        link = attr("infoLink") or {}
        url = None
        if link.get("linkType") == "LINK_TO_ARTICLE_DETAIL_PAGE" and link.get("value"):
            url = f"{BASE_URL}/shop/article/{link['value']}"
        elif link.get("linkType") == "URL" and link.get("value"):
            url = link["value"]

        cover = _image_url(images, attr("image"))

        events.append(
            Event(
                publisher=PUBLISHER,
                author=author,
                title=raw_title,
                date=date_part,
                time=time_part,
                venue=PUBLISHER,
                city="Berlin",
                address=VENUE_ADDRESS,
                url=url or LISTING_URL,
                source_url=LISTING_URL,
                raw_text=f"{event_type}. {description}" if event_type and description else (description or event_type),
                cover_image=cover,
                book_title=book_title,
            )
        )

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
