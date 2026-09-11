"""Scraper for Literaturhaus Berlin, now "Li-Be" (li-be.de) -- a Berlin literature venue.

The old literaturhaus-berlin.de domain is a stale headless-WP frontend that
just points here; li-be.de/programm/ is the live site. Its listing page
already has everything we need (date, time, venue, author+title, subtitle)
server-rendered in one page -- no per-event detail fetch required. Venue
street addresses live on a separate /spielorte/ page, keyed by the same
id used in the event's venue link fragment, so we fetch that once and
build a small lookup table.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, fetch, parse_german_date

LISTING_URL = "https://li-be.de/programm/"
VENUES_URL = "https://li-be.de/spielorte/"
VENUE_ORG = "Literaturhaus Berlin"
MAIN_HOUSE_ADDRESS = "Fasanenstraße 23, 10719 Berlin"


def _venue_addresses() -> dict:
    """Maps venue-id fragment (e.g. "schloss-britz") -> "Street, PLZ City"."""
    try:
        resp = fetch(VENUES_URL)
    except Exception:
        return {}
    soup = BeautifulSoup(resp.text, "lxml")
    lookup = {}
    for article in soup.select("article.venue-article"):
        venue_id = article.get("data-venue-id")
        addr_el = article.select_one(".address")
        if venue_id and addr_el:
            lookup[venue_id] = clean_text(addr_el.get_text())
    return lookup


def _split_author_title(headline: str | None) -> tuple[str | None, str | None]:
    """Headlines are typically "<Author> »<Title>«" -- split on the guillemets."""
    if not headline:
        return None, None
    m = re.match(r"^(.*?)\s*»(.+?)«\s*$", headline)
    if m:
        author = clean_text(m.group(1)) or None
        title = clean_text(m.group(2)) or None
        return author, title
    return None, clean_text(headline)


def scrape() -> list[Event]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")
    venue_addresses = _venue_addresses()

    events: list[Event] = []
    for article in soup.select("article.event-article"):
        date_el = article.select_one(".start-date .meta-date")
        date_iso = parse_german_date(clean_text(date_el.get_text())) if date_el else None

        time_el = article.select_one(".meta--time")
        time_text = clean_text(time_el.get_text()) if time_el else None
        time_str = None
        if time_text:
            m = re.search(r"(\d{1,2}:\d{2})", time_text)
            if m:
                time_str = m.group(1)

        venue_link = article.select_one(".meta--venue a")
        venue_name = clean_text(venue_link.get_text()) if venue_link else VENUE_ORG
        venue_id = None
        if venue_link and venue_link.get("href") and "#" in venue_link["href"]:
            venue_id = venue_link["href"].split("#", 1)[1]
        address = venue_addresses.get(venue_id) if venue_id else None
        if not address:
            address = MAIN_HOUSE_ADDRESS if not venue_id else None

        headline_el = article.select_one("h3.headline a") or article.select_one("h3.headline")
        headline = clean_text(headline_el.get_text()) if headline_el else None
        author, title = _split_author_title(headline)

        subtitle_el = article.select_one(".short-description")
        subtitle = clean_text(subtitle_el.get_text()) if subtitle_el else None

        link_el = article.select_one("h3.headline a") or article.select_one("a.btn-a")
        url = link_el.get("href") if link_el else LISTING_URL

        events.append(
            Event(
                publisher=VENUE_ORG,
                author=author,
                title=title or headline,
                date=date_iso,
                time=time_str,
                venue=venue_name,
                city="Berlin",
                address=address,
                url=url,
                source_url=LISTING_URL,
                raw_text=subtitle,
            )
        )

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
