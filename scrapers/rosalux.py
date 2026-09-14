"""Scraper for the Rosa-Luxemburg-Stiftung (rosalux.de) events.

Unlike Urania/Publix/taz, this site's own category labels cleanly separate
book-related events ("Lesung/Gespräch", "Buchvorstellung") from its many
other event types (Diskussion/Vortrag, Workshop, Seminar, ...), so we
filter on that category text directly instead of guessing from keywords.
Detail pages use schema.org microdata (not JSON-LD) with a full ISO
startDate (date+time together, unlike several other sources here).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://www.rosalux.de/veranstaltungen"
BASE_URL = "https://www.rosalux.de"
PUBLISHER = "Rosa-Luxemburg-Stiftung"

BOOK_CATEGORIES = ("lesung/gespräch", "buchvorstellung")

# "mit dem Autor <Name>", "mit der Autorin <Name>", "Moderation: <Name>" etc.
# -- <strong> tags in the body include real speaker names but also bolded
# contact-block labels ("E-Mail:", "Telefon:"), so this targets the actual
# introduction phrasing instead of trusting every <strong> indiscriminately.
_SPEAKER_PATTERNS = [
    re.compile(r"\bmit\s+(?:dem\s+Autor|der\s+Autorin|den\s+Autor(?:inn)?en)\s+([A-ZÄÖÜ][\wäöüÄÖÜß.\-]+(?:\s+[A-ZÄÖÜ][\wäöüÄÖÜß.\-]+){0,3})"),
    re.compile(r"\bvon\s+([A-ZÄÖÜ][\wäöüÄÖÜß.\-]+(?:\s+[A-ZÄÖÜ][\wäöüÄÖÜß.\-]+){0,3})"),
]


def _looks_like_name(text: str) -> bool:
    if not text or ":" in text or "@" in text:
        return False
    words = text.split()
    return 1 < len(words) <= 4 and all(re.match(r"^[A-ZÄÖÜ][\wäöüÄÖÜß.\-]*$", w) for w in words)


def _parse_detail(url: str) -> dict:
    out: dict = {}
    try:
        resp = fetch(url)
    except Exception:
        return out
    soup = BeautifulSoup(resp.text, "lxml")

    start_meta = soup.select_one('meta[itemprop="startDate"]')
    if start_meta and start_meta.get("content"):
        content = start_meta["content"]
        if len(content) >= 10:
            out["date"] = content[:10]
        if len(content) >= 16:
            out["time"] = content[11:16]

    location = soup.select_one('[itemprop="location"]')
    if location:
        name_el = location.select_one('[itemprop="name"]')
        if name_el:
            out["venue"] = clean_text(name_el.get_text())
        street_el = location.select_one('[itemprop="streetAddress"]')
        postal_el = location.select_one('[itemprop="postalCode"]')
        city_el = location.select_one('[itemprop="addressLocality"]')
        street = clean_text(street_el.get_text()) if street_el else None
        postal = clean_text(postal_el.get_text()) if postal_el else None
        city = clean_text(city_el.get_text()) if city_el else None
        out["city"] = city
        out["address"] = ", ".join(p for p in (street, " ".join(filter(None, [postal, city]))) if p) or None

    body_el = soup.select_one('[itemprop="articleBody"]')
    if body_el:
        description = clean_text(body_el.get_text(" "))
        out["description"] = description

        strong_names = [clean_text(s.get_text()) for s in body_el.select("strong")]
        strong_names = [n for n in strong_names if n and _looks_like_name(n)]
        if not strong_names and description:
            for pattern in _SPEAKER_PATTERNS:
                m = pattern.search(description)
                if m:
                    strong_names = [clean_text(m.group(1))]
                    break
        if strong_names:
            out["speakers"] = ", ".join(dict.fromkeys(strong_names))

    img_el = soup.select_one('img[itemprop="image"]')
    if img_el and img_el.get("src"):
        out["cover"] = img_el["src"]
        caption_el = soup.select_one(".textmedia__copyright")
        if caption_el:
            out["credit"] = clean_text(caption_el.get_text())

    return out


def scrape() -> list[Event]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    events: list[Event] = []
    for section in soup.select('section[data-section^="event-"]'):
        city_el = section.select_one("span.teaser__date-group--right span")
        city = clean_text(city_el.get_text()) if city_el else None
        if not city or city.lower() != "berlin":
            continue

        category_el = section.select_one("span.teaser__meta-event-text")
        category = clean_text(category_el.get_text()) if category_el else None
        if not category or category.lower() not in BOOK_CATEGORIES:
            continue

        link = section.select_one("a.teaser__link")
        if not link or not link.get("href"):
            continue
        href = link["href"]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"

        title_el = section.select_one("span.teaser__title-text")
        title = clean_text(title_el.get_text()) if title_el else None
        teaser_el = section.select_one("p.teaser__text")
        teaser = clean_text(teaser_el.get_text()) if teaser_el else None

        details = _parse_detail(url)

        author = details.get("speakers")
        if not author and teaser:
            for pattern in _SPEAKER_PATTERNS:
                m = pattern.search(teaser)
                if m:
                    author = clean_text(m.group(1))
                    break

        events.append(
            Event(
                publisher=PUBLISHER,
                author=author,
                title=title,
                date=details.get("date"),
                time=details.get("time"),
                venue=details.get("venue") or PUBLISHER,
                city=details.get("city") or city,
                address=details.get("address"),
                url=url,
                source_url=LISTING_URL,
                raw_text=details.get("description") or teaser,
                cover_image=details.get("cover"),
                image_credit=details.get("credit"),
                book_title=extract_quoted_title(title, teaser, details.get("description")),
            )
        )

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
