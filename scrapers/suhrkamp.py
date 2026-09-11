"""Scraper for Suhrkamp Verlag (suhrkamp.de) events.

The page is Next.js SSR; event data ships as JSON inside a
<script id="__NEXT_DATA__"> tag (no separate API endpoint found). Supports
a server-side city filter via ?city_ss=<City> and pagination via ?page=N
(fixed page size of 9).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .base import Event, clean_text, fetch

BASE_URL = "https://www.suhrkamp.de/veranstaltungen/alle-veranstaltungen-s-1113"
PUBLISHER = "Suhrkamp Verlag"
BERLIN_TZ = ZoneInfo("Europe/Berlin")
PAGE_SIZE = 9
MAX_PAGES = 40  # safety cap


def _fetch_page(page: int) -> dict:
    url = f"{BASE_URL}?city_ss=Berlin&page={page}"
    resp = fetch(url)
    html = resp.text
    idx = html.find("__NEXT_DATA__")
    if idx == -1:
        return {}
    start = html.find("{", idx)
    end = html.find("</script>", start)
    try:
        data = json.loads(html[start:end])
    except ValueError:
        return {}
    return data.get("props", {}).get("initialReduxState", {}).get("newsList", {})


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return clean_text(BeautifulSoup(text, "html.parser").get_text(separator=" "))


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%a %b %d %H:%M:%S UTC %Y")
    except ValueError:
        return None
    return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(BERLIN_TZ)


def _item_to_event(item: dict) -> Event:
    date_local = _parse_utc(item.get("date"))
    time_local = _parse_utc(item.get("time"))

    venue = _strip_html(item.get("eventPlace"))
    street = clean_text(item.get("address"))
    postal = clean_text(item.get("postalCode"))
    city = clean_text(item.get("city"))
    address = ", ".join(p for p in (street, " ".join(filter(None, [postal, city]))) if p) or None

    link = item.get("link")
    url = f"https://www.suhrkamp.de{link}" if link and link.startswith("/") else link

    description = _strip_html(item.get("details") or item.get("description"))

    return Event(
        publisher=PUBLISHER,
        author=clean_text(item.get("title")),
        title=description or clean_text(item.get("type")),
        date=date_local.date().isoformat() if date_local else None,
        time=time_local.strftime("%H:%M") if time_local else None,
        venue=venue,
        city=city,
        address=address,
        url=url,
        source_url=BASE_URL,
        raw_text=item.get("type"),
    )


def scrape() -> list[Event]:
    events: list[Event] = []
    page = 1
    total_pages = None
    while page <= MAX_PAGES:
        data = _fetch_page(page)
        items = data.get("items") or []
        if not items:
            break
        events.extend(_item_to_event(i) for i in items)

        if total_pages is None:
            count = data.get("count") or 0
            total_pages = max(1, -(-count // PAGE_SIZE))  # ceil div
        if page >= total_pages:
            break
        page += 1

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
