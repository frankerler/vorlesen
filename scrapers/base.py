"""Shared helpers for all publisher scrapers.

Each publisher scraper module exposes a single function:

    def scrape() -> list[Event]

which fetches that publisher's events/Lesungen page(s) and returns every
event it found. Filtering down to Berlin happens centrally in run.py so
scrapers stay simple and we can later reuse the same raw data for other
cities.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Optional

import requests
from dateutil import parser as dateparser

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 vorlesen-bot/0.1 "
    "(+https://github.com/; personal, non-commercial event aggregator; "
    "contact via publisher site)"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
}

REQUEST_TIMEOUT = 20

# German month names -> number, used for hand-rolled date parsing since
# dateutil doesn't know German month names.
GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5,
    "juni": 6, "juli": 7, "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

# Loose set of spellings/synonyms worth matching when we only have a free-text
# location string (venue name, address line, breadcrumb, etc.) and want to
# know if it's Berlin. Deliberately does NOT match "Berliner ..." publisher
# imprints etc. by itself -- callers should check word boundaries.
BERLIN_PATTERN = re.compile(r"\bberlin\b", re.IGNORECASE)


@dataclass
class Event:
    publisher: str
    author: str
    title: Optional[str]
    date: Optional[str]        # ISO 8601 "YYYY-MM-DD" if known
    time: Optional[str]        # "HH:MM" if known
    venue: Optional[str]
    city: Optional[str]
    address: Optional[str]
    url: Optional[str]
    source_url: str
    raw_text: Optional[str] = None  # fallback: original snippet, for debugging/manual review
    cover_image: Optional[str] = None  # book cover URL, when the source page exposes one
    book_title: Optional[str] = None  # just the book's title, when it can be isolated from `title`

    def id(self) -> str:
        """Stable dedupe key across scraper runs."""
        basis = f"{self.publisher}|{self.author}|{self.date}|{self.venue}|{self.url or self.title}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id()
        return d


def fetch(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT, **kwargs)
    resp.raise_for_status()
    # requests falls back to Latin-1 for text/* responses with no explicit
    # charset in Content-Type, per old HTTP spec defaults -- but every site
    # here actually serves UTF-8, so that fallback mangles umlauts etc.
    # ("FranÃ§oise" instead of "Françoise"). Only override when the server
    # didn't declare a charset; respect it when it did.
    content_type = resp.headers.get("Content-Type", "")
    if "charset" not in content_type.lower():
        resp.encoding = "utf-8"
    return resp


def is_berlin(*fragments: Optional[str]) -> bool:
    """True if any of the given free-text fragments mentions Berlin as a place."""
    for frag in fragments:
        if frag and BERLIN_PATTERN.search(frag):
            return True
    return False


def parse_german_date(text: str, default_year: Optional[int] = None) -> Optional[str]:
    """Parse dates like '12. September 2026', '12.09.2026', '12.09.', 'Fr, 12.09.2026'.

    Returns ISO 'YYYY-MM-DD' or None if unparseable.
    """
    if not text:
        return None
    text = text.strip()

    # "12. September 2026" / "12. September" (no year -> assume current/next occurrence)
    m = re.search(
        r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)\.?\s*(\d{4})?",
        text,
    )
    if m:
        day, month_name, year = m.groups()
        month_key = month_name.lower().strip(".")
        month = GERMAN_MONTHS.get(month_key)
        if month:
            year_int = int(year) if year else (default_year or _infer_year(int(day), month))
            try:
                return date(year_int, month, int(day)).isoformat()
            except ValueError:
                return None

    # "12.09.2026" or "12.09.26" or "12.9.2026"
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text)
    if m:
        day, month, year = m.groups()
        year_int = int(year)
        if year_int < 100:
            year_int += 2000
        try:
            return date(year_int, int(month), int(day)).isoformat()
        except ValueError:
            return None

    # "12.09." without year
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(?!\d)", text)
    if m:
        day, month = m.groups()
        year_int = default_year or _infer_year(int(day), int(month))
        try:
            return date(year_int, int(month), int(day)).isoformat()
        except ValueError:
            return None

    # Fall back to dateutil for ISO-ish or English-ish strings.
    try:
        dt = dateparser.parse(text, dayfirst=True, fuzzy=True, default=datetime(default_year or date.today().year, 1, 1))
        return dt.date().isoformat()
    except (ValueError, OverflowError):
        return None


def _infer_year(day: int, month: int) -> int:
    """Given only day/month, assume the next occurrence of that date (today or future)."""
    today = date.today()
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return today.year
    if candidate < today:
        return today.year + 1
    return today.year


def clean_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return re.sub(r"\s+", " ", s).strip() or None


# Sources that don't expose a clean, separate "book title" field usually still
# have it quoted/set off somewhere in their free-text title or description --
# German »guillemets« and ›single guillemets‹ are the most common, but plain
# and curly quotes show up too. We take the *longest* quoted match across all
# given texts, on the theory that a short quoted aside is rarely the title
# but a book title usually is the longest quoted phrase in the sentence.
_QUOTE_PATTERNS = [
    re.compile(r"»([^»«]{3,140})«"),
    re.compile(r"›([^›‹]{3,140})‹"),
    re.compile(r"„([^„“]{3,140})“"),
    re.compile(r'"([^"]{3,140})"'),
]


def extract_quoted_title(*texts: Optional[str]) -> Optional[str]:
    """Best-effort extraction of a book title quoted inside free text."""
    best = None
    for text in texts:
        if not text:
            continue
        for pattern in _QUOTE_PATTERNS:
            for m in pattern.finditer(text):
                candidate = clean_text(m.group(1))
                if candidate and (best is None or len(candidate) > len(best)):
                    best = candidate
    return best


# --- Cross-source fuzzy matching -------------------------------------------
#
# The same real-world reading is often listed independently by (a) the
# book's publisher and (b) the venue hosting it -- e.g. a Suhrkamp author
# event at "Literarisches Colloquium Berlin" shows up both in Suhrkamp's own
# scrape (as a venue string) and in the LCB venue scraper's own listing.
# Since the two sources rarely agree on exact spelling/punctuation, an exact
# string/id match (see Event.id()) won't catch these -- run.py uses the
# helpers below for a fuzzier "is this probably the same event" check.

_ACCENTS = str.maketrans({
    "ä": "a", "ö": "o", "ü": "u", "Ä": "A", "Ö": "O", "Ü": "U", "ß": "s",
    "à": "a", "á": "a", "â": "a", "ã": "a", "å": "a",
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "í": "i", "ì": "i", "î": "i", "ï": "i",
    "ó": "o", "ò": "o", "ô": "o", "õ": "o",
    "ú": "u", "ù": "u", "û": "u",
    "ý": "y", "ñ": "n", "ç": "c", "ÿ": "y", "œ": "o", "æ": "a",
})


def _fold(s: str) -> str:
    return s.translate(_ACCENTS).lower()


def normalize_venue(venue: Optional[str]) -> str:
    """Lowercased, accent-folded, punctuation-stripped venue name for fuzzy matching."""
    if not venue:
        return ""
    s = _fold(venue)
    s = re.sub(r"\b(e\.?\s?v\.?|gmbh|theater|buchhandlung)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def venues_match(a: Optional[str], b: Optional[str]) -> bool:
    """True if two venue strings plausibly refer to the same place."""
    na, nb = normalize_venue(a), normalize_venue(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    # Word-overlap fallback for things like "Colosseum" vs "Filmtheater Colosseum".
    wa, wb = set(na.split()), set(nb.split())
    significant = {w for w in wa & wb if len(w) >= 4}
    return bool(significant)


def name_tokens(name: Optional[str]) -> set:
    """Splits a (possibly multi-author) name string into normalized name tokens.

    "Ruth-Maria Thomas, Cynthia Cornelius" -> {"ruth", "maria", "thomas", "cynthia", "cornelius"}
    so "Ruth Maria Thomas" (no hyphen) from another source still overlaps.
    """
    if not name:
        return set()
    folded = _fold(name)
    parts = re.split(r"[,;/&]|(?:\bund\b)|(?:\bmit\b)|(?:\bim gespräch\b)", folded)
    tokens = set()
    for part in parts:
        for word in re.split(r"[\s\-]+", part.strip()):
            word = re.sub(r"[^a-z0-9]", "", word)
            if len(word) >= 3:
                tokens.add(word)
    return tokens


def authors_overlap(a: Optional[str], b: Optional[str]) -> bool:
    """True if two author strings share at least one name token (first or last name)."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    return bool(ta & tb)
