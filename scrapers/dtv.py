"""Scraper for dtv Verlag (dtv.de) events.

dtv.de is Shopware-based and server-renders events with schema.org/Event
microdata -- the friendliest site in this project so far. It also supports
a server-side ?city= filter and pagination via ?p=.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, fetch

BASE_URL = "https://www.dtv.de/events"
PUBLISHER = "dtv Verlag"
MAX_PAGES = 10  # safety cap; site had ~5 pages total unfiltered at research time


def _extract_author(title: str | None, author_link_href: str | None) -> str | None:
    if title:
        # Titles are typically "Author liest aus ›Buchtitel‹" / "Author liest ..."
        m = re.match(r"^(.*?)\s+liest\b", title, re.IGNORECASE)
        if m:
            return clean_text(m.group(1))
    if author_link_href:
        # /autor/erin-entrada-kelly-9058 -> "Erin Entrada Kelly"
        slug = author_link_href.rstrip("/").rsplit("/", 1)[-1]
        slug = re.sub(r"-\d+$", "", slug)  # drop trailing id
        name = " ".join(part.capitalize() for part in slug.split("-"))
        return clean_text(name) or None
    return None


def _parse_page(html: str, source_url: str) -> list[Event]:
    soup = BeautifulSoup(html, "lxml")
    events: list[Event] = []

    for box in soup.select("div.pondus-event-box"):
        title_el = box.select_one(".pondus-event-box-title")
        title = clean_text(title_el.get_text()) if title_el else None

        date_el = box.select_one(".event-date")
        time_el = box.select_one(".event-time")
        date_text = clean_text(date_el.get_text()) if date_el else None
        time_text = clean_text(time_el.get_text()) if time_el else None

        start_meta = box.select_one('meta[itemprop="startDate"]')
        iso_date = None
        if start_meta and start_meta.get("content"):
            iso_date = start_meta["content"][:10]  # "2026-09-11T18:00:00+02:00" -> date part

        address_el = box.select_one("address.event-address")
        venue = street = postal = city = None
        if address_el:
            # Layout: <address><span class="icon">…</span><div><span>Venue</span><br/>
            # <span itemprop="streetAddress">…</span><br/><span itemprop="postalCode">…</span>
            # <span itemprop="addressLocality">…</span></div></address>
            inner = address_el.find("div") or address_el
            spans = [s for s in inner.find_all("span", recursive=False) if not s.get("itemprop")]
            venue = clean_text(spans[0].get_text()) if spans else None
            street_el = address_el.select_one('[itemprop="streetAddress"]')
            postal_el = address_el.select_one('[itemprop="postalCode"]')
            city_el = address_el.select_one('[itemprop="addressLocality"]')
            street = clean_text(street_el.get_text()) if street_el else None
            postal = clean_text(postal_el.get_text()) if postal_el else None
            city = clean_text(city_el.get_text()) if city_el else None

        address = ", ".join(p for p in (street, " ".join(filter(None, [postal, city]))) if p) or None

        author_link = box.select_one('.pondus-event-box-actions a[href*="/autor/"]')
        author = _extract_author(title, author_link.get("href") if author_link else None)

        img_el = box.select_one("img.pondus-event-image, img")
        cover = None
        if img_el:
            cover = img_el.get("src") or img_el.get("data-src")

        link_el = box.select_one(".event-link a[itemprop='url']") or box.select_one(".event-link a")
        url = link_el.get("href") if link_el else None
        if not url:
            book_link = box.select_one('.pondus-event-box-actions a[href*="/buch/"]')
            url = book_link.get("href") if book_link else None

        events.append(
            Event(
                publisher=PUBLISHER,
                author=author,
                title=title,
                date=iso_date,
                time=time_text.replace("Uhr", "").replace("(CEST)", "").replace("(CET)", "").strip() if time_text else None,
                venue=venue,
                city=city,
                address=address,
                url=url,
                source_url=source_url,
                raw_text=" / ".join(filter(None, [date_text, time_text])),
                cover_image=cover,
            )
        )

    return events


def scrape() -> list[Event]:
    all_events: list[Event] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE_URL}?city=Berlin&p={page}"
        resp = fetch(url)
        page_events = _parse_page(resp.text, url)
        if not page_events:
            break
        all_events.extend(page_events)
        if len(page_events) < 20:
            # last page (dtv shows ~24/page; a short page signals the end)
            break

    return all_events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
