"""Scraper for Dussmann das KulturKaufhaus (kulturkaufhaus.de) book events.

The /buchevent listing already isolates book-related events from the
venue's other event types (concerts, workshops, ...) via the URL path
itself, and currently fits on one page (no pagination seen). Author name
isn't a separate field anywhere (JSON-LD `performer.name` is empty on
every event checked) -- it's parsed out of the heading text ("... mit
<Name>"), which is the venue's own convention for phrasing these.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch, image_from_schema_org

LISTING_URL = "https://www.kulturkaufhaus.de/de/veranstaltungen/buchevent"
BASE_URL = "https://www.kulturkaufhaus.de"
PUBLISHER = "Dussmann das KulturKaufhaus"

# Headings are prefixed with a status flag when relevant, e.g.
# "AUSVERKAUFT // Buchvorstellung mit X" or "ABGESAGT // ...".
_STATUS_PREFIX_RE = re.compile(r"^(AUSVERKAUFT|ABGESAGT)\s*//\s*", re.IGNORECASE)
_AUTHOR_RE = re.compile(r"\bmit\s+(.+)$", re.IGNORECASE)


def _extract_author(heading: str | None) -> str | None:
    if not heading:
        return None
    m = _AUTHOR_RE.search(heading)
    return clean_text(m.group(1)) if m else None


def _detail_links() -> list[str]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")
    links = []
    for h in soup.select("div.eventArticle h3.articleHeading a[href]"):
        href = h["href"]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if url not in links:
            links.append(url)
    return links


def _parse_detail(url: str) -> Event | None:
    try:
        resp = fetch(url)
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "lxml")

    event_data = None
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        about = data.get("about") if isinstance(data, dict) else None
        if isinstance(about, dict) and about.get("@type") == "Event":
            event_data = about
            break
    if not event_data:
        return None

    raw_name = clean_text(event_data.get("name"))
    status_match = _STATUS_PREFIX_RE.match(raw_name or "")
    heading = _STATUS_PREFIX_RE.sub("", raw_name).strip() if raw_name else None
    status = clean_text(status_match.group(1)) if status_match else None

    start = event_data.get("startDate") or ""
    date_part = start[:10] if len(start) >= 10 else None
    time_part = start[11:16] if len(start) >= 16 else None

    location = event_data.get("location") or {}
    venue = clean_text(location.get("name")) or "KulturKaufhaus"
    addr = location.get("address") or {}
    street = clean_text(addr.get("streetAddress"))
    postal = str(addr.get("postalCode") or "").strip() or None
    city = clean_text(addr.get("addressLocality")) or "Berlin"
    address = ", ".join(p for p in (street, " ".join(filter(None, [postal, city]))) if p) or None

    images = event_data.get("image") or []
    if isinstance(images, str):
        images = [images]
    cover = None
    credit = None
    for img in images:
        cover, credit = image_from_schema_org(img)
        if cover:
            break

    author = _extract_author(heading)
    book_title = extract_quoted_title(heading)

    # The page also has a sitewide newsletter-signup blurb using this same
    # class outside the article -- scope to div.articleDetail to skip it.
    body_el = soup.select_one("div.articleDetail div.articleHtmlText")
    description = clean_text(body_el.get_text(" ")) if body_el else None
    if status:
        description = f"{status}. {description}" if description else status

    return Event(
        publisher=PUBLISHER,
        author=author,
        title=heading,
        date=date_part,
        time=time_part,
        venue=venue,
        city=city,
        address=address,
        url=url,
        source_url=LISTING_URL,
        raw_text=description,
        cover_image=cover,
        image_credit=credit,
        book_title=book_title,
    )


def scrape() -> list[Event]:
    events: list[Event] = []
    for url in _detail_links():
        event = _parse_detail(url)
        if event:
            events.append(event)
    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
