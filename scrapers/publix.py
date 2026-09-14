"""Scraper for Publix (publix.de) -- a journalism/media/democracy venue in
Berlin-Neukölln that, alongside talks and panels, hosts book launches and
author readings. Category tags on the site (Publix Thursday/Publix Event/
Gastveranstaltung) don't map cleanly to "literary event", so -- like
Urania -- we keep only entries that look like book events by keyword.
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

BASE_URL = "https://www.publix.de"
LISTING_URL = f"{BASE_URL}/en/events"
PUBLISHER = "Publix"
VENUE_ADDRESS = "Hermannstraße 90, 12051 Berlin"
MAX_PAGES = 10

LITERARY_KEYWORDS = ("book launch", "buchpremiere", "book presentation", "reading", "lesung", "buchvorstellung")


def _is_literary(*texts: str | None) -> bool:
    combined = " ".join(t for t in texts if t).lower()
    return any(kw in combined for kw in LITERARY_KEYWORDS)


def _parse_start(raw: str | None) -> tuple[str | None, str | None]:
    """Publix's meta content is a non-standard "YYYY-MM-DDTH:MM AM/PM" string."""
    if not raw:
        return None, None
    try:
        dt = datetime.strptime(raw.strip(), "%Y-%m-%dT%I:%M %p")
        return dt.date().isoformat(), dt.strftime("%H:%M")
    except ValueError:
        pass
    # Fallback: just grab the date part if the time format is unexpected.
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    return (m.group(1) if m else None), None


def _parse_detail(url: str) -> dict:
    out: dict = {}
    try:
        resp = fetch(url)
    except Exception:
        return out
    soup = BeautifulSoup(resp.text, "lxml")

    performers = [clean_text(p.get_text()) for p in soup.select('[itemprop="performer"]')]
    performers = [p for p in performers if p]
    if performers:
        out["author"] = ", ".join(performers)

    desc_paragraphs = soup.select("p.text-body-18, p.text-body-20")
    if desc_paragraphs:
        out["description"] = clean_text(" ".join(p.get_text(" ") for p in desc_paragraphs))

    return out


def scrape() -> list[Event]:
    events: list[Event] = []
    seen_hrefs: set[str] = set()

    for page in range(1, MAX_PAGES + 1):
        url = LISTING_URL if page == 1 else f"{LISTING_URL}/p{page}"
        resp = fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select('a[itemtype="https://schema.org/Event"]')
        if not cards:
            break

        # Out-of-range pages on this site redirect back to page 1's content
        # instead of returning empty -- a plain "no cards" or "< 5 cards"
        # check doesn't catch that, so stop as soon as a page contributes
        # nothing new instead of trusting the card count.
        page_hrefs = {c.get("href") for c in cards if c.get("href")}
        if page_hrefs and page_hrefs <= seen_hrefs:
            break

        new_hrefs = page_hrefs - seen_hrefs
        seen_hrefs |= page_hrefs

        for card in cards:
            href = card.get("href")
            if href not in new_hrefs:
                continue  # already processed on an earlier page

            title_el = card.select_one('[itemprop="name"]')
            title = clean_text(title_el.get_text()) if title_el else None
            subtitle_el = card.select_one("h4")
            subtitle = clean_text(subtitle_el.get_text()) if subtitle_el else None

            if not _is_literary(title, subtitle):
                continue

            start_meta = card.select_one('meta[itemprop="startDate"]')
            date_part, time_part = _parse_start(start_meta.get("content") if start_meta else None)

            detail_url = href if (href and href.startswith("http")) else (f"{BASE_URL}{href}" if href else None)

            details = _parse_detail(detail_url) if detail_url else {}

            events.append(
                Event(
                    publisher=PUBLISHER,
                    author=details.get("author"),
                    title=title,
                    date=date_part,
                    time=time_part,
                    venue=PUBLISHER,
                    city="Berlin",
                    address=VENUE_ADDRESS,
                    url=detail_url or LISTING_URL,
                    source_url=LISTING_URL,
                    raw_text=details.get("description") or subtitle,
                    book_title=extract_quoted_title(title, subtitle, details.get("description")),
                )
            )

        if len(cards) < 5:
            break

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
