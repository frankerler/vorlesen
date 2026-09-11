"""Scraper for Literarisches Colloquium Berlin (lcb.de) -- a Berlin literature venue.

Listing page has the same event list rendered twice (a mobile sidebar copy
and a desktop "fullwidth" copy) -- we only read the fullwidth one to avoid
scraping duplicates from a single page. Detail pages have a clean labelled
h4/p sidebar (date, "Ort", "Teilnehmer•innen") which is the primary data
source; there's no schema.org/Event JSON-LD here, only generic SEO schema.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch, parse_german_date

LISTING_URL = "https://lcb.de/category/veranstaltungen/"
VENUE = "Literarisches Colloquium Berlin"
DEFAULT_ADDRESS = "Am Sandwerder 5, 14109 Berlin"
BASE_URL = "https://lcb.de"


def _detail_urls() -> list[str]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")
    ul = soup.select_one("ul.list--events--fullwidth")
    if not ul:
        return []
    urls = []
    for li in ul.select("li.list__item"):
        if "list__header" in (li.get("class") or []):
            continue
        link = li.find("a", href=True)
        if link and link["href"] not in urls:
            urls.append(link["href"])
    return urls


def _sidebar_pairs(text_div) -> dict:
    """The h4/p sidebar is a flat sequence of label/value pairs (h4=label, p=value)."""
    pairs = {}
    children = [c for c in text_div.find_all(["h4", "p"], recursive=False)]
    i = 0
    while i < len(children) - 1:
        label_el, value_el = children[i], children[i + 1]
        if label_el.name == "h4" and value_el.name == "p":
            label = clean_text(label_el.get_text())
            pairs[label] = value_el
            i += 2
        else:
            i += 1
    return pairs


def _parse_detail(url: str) -> Event | None:
    try:
        resp = fetch(url)
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "lxml")

    title_el = soup.select_one(".grid-cell-6 h1")
    title = clean_text(title_el.get_text()) if title_el else None

    # No dedicated book-title field; the description paragraphs often bold
    # the book's title (e.g. "... aus ihrem Roman <strong>Titel</strong>"),
    # which is a better signal here than trying to quote-match the headline.
    book_title = None
    for strong in soup.select(".grid-cell-6 p strong"):
        candidate = clean_text(strong.get_text())
        if candidate and len(candidate) >= 3:
            book_title = candidate
            break
    if not book_title:
        book_title = extract_quoted_title(title)

    text_div = soup.select_one(".grid-cell-2 .text") or soup.select_one(".grid-cell-2.pl-30 .text")
    if not text_div:
        return None
    pairs = _sidebar_pairs(text_div)

    date_iso = None
    time_str = None
    # The date h4 is identified by its class, not its text -- find it directly.
    date_h4 = text_div.select_one("h4.h4--date")
    if date_h4:
        date_iso = parse_german_date(clean_text(date_h4.get_text()))
        time_p = date_h4.find_next_sibling("p")
        if time_p:
            m = re.search(r"(\d{1,2}:\d{2})", time_p.get_text())
            if m:
                time_str = m.group(1)

    venue = VENUE
    address = DEFAULT_ADDRESS
    ort_p = pairs.get("Ort")
    if ort_p:
        parts = [clean_text(p) for p in ort_p.get_text().split("·")]
        parts = [p for p in parts if p]
        if parts:
            venue = parts[0]
        if len(parts) > 1:
            address = ", ".join(parts[1:])

    author = None
    for label in ("Teilnehmer•innen", "Teilnehmerinnen", "Teilnehmer"):
        participants_p = pairs.get(label)
        if participants_p:
            names = [clean_text(a.get_text()) for a in participants_p.find_all("a")]
            names = [n for n in names if n]
            if names:
                author = ", ".join(names)
            break

    return Event(
        publisher=VENUE,
        author=author,
        title=title,
        date=date_iso,
        time=time_str,
        venue=venue,
        city="Berlin",
        address=address,
        url=url,
        source_url=LISTING_URL,
        raw_text=None,
        book_title=book_title,
    )


def scrape() -> list[Event]:
    events: list[Event] = []
    for url in _detail_urls():
        event = _parse_detail(url)
        if event:
            events.append(event)
    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
