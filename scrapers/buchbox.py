"""Scraper for Buchbox! Berlin (buchboxberlin.de) events.

Drupal 7 site, fully server-rendered, paginated via ?page=N (0-indexed).
No JSON-LD anywhere on the site -- everything comes from class-named divs.
Author name is best-effort: only present as structured text when a specific
book is tagged to the event (the "bibliografie" block on the detail page);
otherwise we fall back to regexing "mit <Name>" out of the title.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://buchboxberlin.de/veranstaltungen"
BASE_URL = "https://buchboxberlin.de"
PUBLISHER = "Buchbox! Berlin"
MAX_PAGES = 15  # safety cap

_AUTHOR_RE = re.compile(r"\bmit\s+(.+?)(?:\s*[!.]?\s*$)", re.IGNORECASE)


def _extract_author_from_title(title: str | None) -> str | None:
    if not title:
        return None
    m = _AUTHOR_RE.search(title)
    return clean_text(m.group(1)) if m else None


def _listing_cards(page: int) -> list:
    url = LISTING_URL if page == 0 else f"{LISTING_URL}?page={page}"
    resp = fetch(url)
    soup = BeautifulSoup(resp.text, "lxml")
    return soup.select("div.veranstaltungbuchbox.overview")


def _parse_detail(url: str, fallback_title: str | None, fallback_date: str | None,
                   fallback_time: str | None, fallback_cover: str | None) -> Event:
    author = None
    venue = None
    address = None
    description = None
    book_title = None
    cover = fallback_cover

    try:
        resp = fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        addr_el = soup.select_one("div.address p") or soup.select_one("div.address")
        if addr_el:
            venue = clean_text(addr_el.get_text(" "))
            address = venue  # this site only exposes one free-text address/venue line

        text_el = soup.select_one("div.text")
        if text_el:
            description = clean_text(text_el.get_text(" "))

        author_el = soup.select_one("div.bhw_bootstrap_theme_listitem_author a")
        if author_el:
            # "Lastname, Firstname" -> "Firstname Lastname"
            raw = clean_text(author_el.get_text())
            if raw and "," in raw:
                last, first = (p.strip() for p in raw.split(",", 1))
                author = f"{first} {last}".strip()
            else:
                author = raw

        title_el = soup.select_one("div.bhw_bootstrap_theme_listitem_titel")
        if title_el:
            book_title = clean_text(title_el.get_text())

        cover_el = soup.select_one("div.bhw_bootstrap_theme_listitem_cover img")
        if cover_el and cover_el.get("src"):
            cover = cover_el["src"]
    except Exception:
        pass

    if not author:
        author = _extract_author_from_title(fallback_title)
    if not book_title:
        book_title = extract_quoted_title(fallback_title, description)

    return Event(
        publisher=PUBLISHER,
        author=author,
        title=fallback_title,
        date=fallback_date,
        time=fallback_time,
        venue=venue or PUBLISHER,
        city="Berlin",
        address=address,
        url=url,
        source_url=LISTING_URL,
        raw_text=description,
        cover_image=cover,
        book_title=book_title,
    )


def scrape() -> list[Event]:
    events: list[Event] = []
    seen_urls = set()

    for page in range(MAX_PAGES):
        cards = _listing_cards(page)
        if not cards:
            break

        for card in cards:
            detail_href = card.get("data-href")
            if not detail_href:
                continue
            detail_url = detail_href if detail_href.startswith("http") else f"{BASE_URL}{detail_href}"
            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)

            title_el = card.select_one("div.title a")
            title = clean_text(title_el.get_text()) if title_el else None

            date_spans = card.select("span.date-display-single[content]")
            date_part = time_part = None
            if date_spans:
                iso = date_spans[0].get("content") or ""
                date_part = iso[:10] if len(iso) >= 10 else None
                time_part = iso[11:16] if len(iso) >= 16 else None

            cover_el = card.select_one("img.img-responsive")
            cover = cover_el.get("src") if cover_el else None

            events.append(_parse_detail(detail_url, title, date_part, time_part, cover))

        if len(cards) < 5:  # short page -- likely the last one
            break

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
