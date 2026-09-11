"""Scraper for Piper Verlag (piper.de) events.

Listing page ships all events server-rendered in one page as
`div.m-event__listitem` blocks with rich data-* attributes (author, city,
zip, rough address, event type) plus a link to a detail page.

The detail page has clean labelled fields (Art/Datum/Zeit/Ort/Autor/...)
and is where we get the exact time and a clean venue name. To keep this
fast/polite we only fetch detail pages for events whose listing already
looks like Berlin (data-town == "berlin"), since that's all we need for
this app -- see run.py for city filtering in general.
"""
from __future__ import annotations

import base64
import time

from bs4 import BeautifulSoup

from .base import Event, clean_text, fetch, parse_german_date

LISTING_URL = "https://www.piper.de/autoren/veranstaltungen"
PUBLISHER = "Piper Verlag"
REQUEST_DELAY_SECONDS = 0.5


def _decode_data_href(span) -> str | None:
    if span is None:
        return None
    encoded = span.get("data-href")
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return None


def _parse_detail(url: str) -> dict:
    """Fetch a detail page and return clean fields: venue, address, city, time, url."""
    out: dict = {}
    try:
        resp = fetch(url)
    except Exception:
        return out
    soup = BeautifulSoup(resp.text, "lxml")

    img_el = soup.select_one(".m-eventdetail img, figure img")
    if img_el and img_el.get("src"):
        src = img_el["src"]
        out["cover_image"] = f"https://www.piper.de{src}" if src.startswith("/") else src

    for item in soup.select(".m-eventdetail__eventsnippet__item"):
        divs = item.find_all("div", recursive=False)
        if len(divs) < 2:
            continue
        label = clean_text(divs[0].get_text())
        value_div = item.select_one(".value") or divs[1]

        if label and label.rstrip(":").lower() == "zeit":
            time_text = clean_text(value_div.get_text())
            if time_text:
                out["time"] = time_text.replace("Uhr", "").strip()

        elif label and label.rstrip(":").lower() == "ort":
            # venue name, street, "plz city" separated by <br>
            parts = [clean_text(p) for p in value_div.decode_contents().split("<br/>")]
            parts = [BeautifulSoup(p, "lxml").get_text(strip=True) for p in parts if p]
            parts = [p.rstrip(",").strip() for p in parts if p]
            if parts:
                out["venue"] = parts[0]
            if len(parts) > 1:
                out["address"] = ", ".join(parts[1:])
            if len(parts) > 1 and "berlin" in parts[-1].lower():
                out["city"] = "Berlin"

        elif label and label.rstrip(":").lower() == "links":
            span = value_div.find(attrs={"data-href": True})
            decoded = _decode_data_href(span)
            if decoded:
                out["ticket_url"] = decoded

    return out


def scrape() -> list[Event]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    events: list[Event] = []
    for item in soup.select("div.m-event__listitem"):
        city = clean_text(item.get("data-town", "")) or None
        author = clean_text(item.get("data-author", "")) or None
        address = clean_text(item.get("data-address", "")) or None

        title_el = item.select_one(".m-event__listitem__title a")
        title = clean_text(title_el.get_text()) if title_el else None
        detail_url = title_el.get("href") if title_el else None

        date_el = item.select_one(".m-event__listitem__date")
        date_text = clean_text(date_el.get_text()) if date_el else None
        event_date = parse_german_date(date_text) if date_text else None

        # Proper-case the author for display (data-author is lowercase).
        display_author = author.title() if author else None

        event = Event(
            publisher=PUBLISHER,
            author=display_author,
            title=title,
            date=event_date,
            time=None,
            venue=None,
            city=city.title() if city else None,
            address=address,
            url=detail_url,
            source_url=LISTING_URL,
            raw_text=date_text,
        )

        # Only worth the extra request (venue/time/ticket link) for Berlin events.
        if city and city.lower() == "berlin" and detail_url:
            time.sleep(REQUEST_DELAY_SECONDS)
            details = _parse_detail(detail_url)
            if details.get("time"):
                event.time = details["time"]
            if details.get("venue"):
                event.venue = details["venue"]
            if details.get("address"):
                event.address = details["address"]
            if details.get("ticket_url"):
                event.url = details["ticket_url"]
            if details.get("cover_image"):
                event.cover_image = details["cover_image"]

        events.append(event)

    return events


if __name__ == "__main__":
    for e in scrape():
        if e.city and e.city.lower() == "berlin":
            print(e.to_dict())
