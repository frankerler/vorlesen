"""Scraper for taz (die tageszeitung, taz.de) talks/events.

taz runs an ongoing public events calendar (taz Talk, taz Salon, taz
Kantine/Bundestalk) -- not every one of these is about a book, so (like
Urania/Publix) we keep only entries that look like a book
reading/presentation by keyword. The "Aktuelle" (current) tab already
contains every upcoming event in one page load (client-side pagination
only), so no pagination is needed.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from .base import Event, clean_text, extract_quoted_title, fetch

LISTING_URL = "https://taz.de/taz-talks-und-events/!v=a0be61fd-26bc-43aa-b2ef-0e030355a949&vp=6180711/"
BASE_URL = "https://taz.de"
PUBLISHER = "taz"

LITERARY_KEYWORDS = ("buch", "book", "roman", "liest", "lesung", "autor", "author", "buchmesse")

_TIME_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*Uhr", re.IGNORECASE)
_SPEAKER_RE = re.compile(r"🐾\s*([A-ZÄÖÜ][\wäöüÄÖÜß.\-]+(?:\s+[A-ZÄÖÜ][\wäöüÄÖÜß.\-]+){0,3})")
# taz Talks happen all over (taz Kantine in Berlin, but also e.g. the
# Frankfurt Book Fair, or livestream-only) -- pull the actual city out of
# the venue text rather than assuming Berlin, so run.py's Berlin filter
# isn't fooled into keeping an out-of-town event.
_CITY_RE = re.compile(r"\b\d{5}\s+([A-ZÄÖÜ][\wÄÖÜäöüß.\- ]*?)(?=\s+Deutschland\b|$)")


def _is_literary(*texts: str | None) -> bool:
    combined = " ".join(t for t in texts if t).lower()
    return any(kw in combined for kw in LITERARY_KEYWORDS)


def _parse_detail(url: str) -> dict:
    out: dict = {}
    try:
        resp = fetch(url)
    except Exception:
        return out
    soup = BeautifulSoup(resp.text, "lxml")

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("@type") == "NewsArticle":
            published = data.get("datePublished") or ""
            if len(published) >= 10:
                out["date"] = published[:10]
            if len(published) >= 16:
                out["time"] = published[11:16]
            out["description"] = clean_text(data.get("description"))
            break

    info_block = soup.select_one("div.typo-short-text")
    if info_block:
        paragraphs = [clean_text(p.get_text(" ")) for p in info_block.select("p")]
        paragraphs = [p for p in paragraphs if p]

        wo_idx = next((i for i, p in enumerate(paragraphs) if p.lower().startswith("wo")), None)
        if wo_idx is not None:
            venue_name = re.sub(r"^wo:\s*", "", paragraphs[wo_idx], flags=re.IGNORECASE)
            # Address usually continues in the next 1-2 paragraphs (street,
            # then "PLZ City") until a new labelled field starts.
            address_parts = []
            for p in paragraphs[wo_idx + 1: wo_idx + 3]:
                if re.match(r"^[a-zäöü]+:", p, re.IGNORECASE) or re.search(r"eintritt|anmeldung|einlass", p, re.IGNORECASE):
                    break
                address_parts.append(p)
            full_address_text = " ".join([venue_name, *address_parts])

            out["venue_text"] = venue_name
            if address_parts:
                out["address"] = ", ".join(address_parts)

            city_match = _CITY_RE.search(full_address_text)
            if re.search(r"\bberlin\b", full_address_text, re.IGNORECASE):
                out["city"] = "Berlin"
            elif city_match:
                out["city"] = clean_text(city_match.group(1))

        for p in paragraphs:
            tm = _TIME_RE.search(p)
            if tm and "time" not in out:
                out["time"] = f"{int(tm.group(1)):02d}:{tm.group(2)}"

    body_text = soup.get_text(" ")
    speakers = _SPEAKER_RE.findall(body_text)
    if speakers:
        out["speakers"] = ", ".join(dict.fromkeys(clean_text(s) for s in speakers))  # dedupe, keep order

    return out


def scrape() -> list[Event]:
    resp = fetch(LISTING_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    events: list[Event] = []
    for article in soup.select("article.article-teaser"):
        link = article.select_one("a[href]")
        if not link:
            continue
        href = link["href"]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"

        title_el = article.select_one("p.headline")
        title = clean_text(title_el.get_text()) if title_el else None
        subtitle_el = article.select_one("div.typo-subline")
        subtitle = clean_text(subtitle_el.get_text()) if subtitle_el else None
        topline_el = article.select_one("p.typo-topline")
        topline = clean_text(topline_el.get_text()) if topline_el else None

        if not _is_literary(title, subtitle, topline):
            continue

        details = _parse_detail(url)

        events.append(
            Event(
                publisher=PUBLISHER,
                author=details.get("speakers"),
                title=title,
                date=details.get("date"),
                time=details.get("time"),
                venue=details.get("venue_text") or PUBLISHER,
                city=details.get("city"),
                address=details.get("address"),
                url=url,
                source_url=LISTING_URL,
                raw_text=details.get("description") or subtitle,
                book_title=extract_quoted_title(title, subtitle, details.get("description")),
            )
        )

    return events


if __name__ == "__main__":
    for e in scrape():
        print(e.to_dict())
