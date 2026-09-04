#!/usr/bin/env python3
"""Build the local Tanakh dataset used by the app.

Downloads the 39 Hebrew book files of the "Tanach with Ta'amei Hamikra" version
from Sefaria's public export bucket and writes them into a single gzipped JSON
file at ``data/tanakh.json.gz``.

This script is a *build-time* tool. Run it once (or whenever you want to refresh
the corpus); the resulting file is committed to the repository, and the running
application never touches the network.

    python scripts/build_dataset.py

Source : https://github.com/Sefaria/Sefaria-Export  (text originally from tanach.us)
License: Public Domain
"""

from __future__ import annotations

import concurrent.futures
import re
import gzip
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BUCKET = "https://storage.googleapis.com/sefaria-export/json/Tanakh"
VERSION_FILE = "Tanach with Ta'amei Hamikra.json"

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "tanakh.json.gz"

# The 24 books of the Tanakh in canonical order, as the 39 files Sefaria splits
# them into. Order matters: verse adjacency (used by the couples search) is
# derived from this sequence, and Samuel/Kings/Chronicles are kept as separate
# books so a pair never spans the seam between two of them.
BOOKS: list[tuple[str, str]] = [
    # (Sefaria section, Sefaria book name)
    ("Torah", "Genesis"),
    ("Torah", "Exodus"),
    ("Torah", "Leviticus"),
    ("Torah", "Numbers"),
    ("Torah", "Deuteronomy"),
    ("Prophets", "Joshua"),
    ("Prophets", "Judges"),
    ("Prophets", "I Samuel"),
    ("Prophets", "II Samuel"),
    ("Prophets", "I Kings"),
    ("Prophets", "II Kings"),
    ("Prophets", "Isaiah"),
    ("Prophets", "Jeremiah"),
    ("Prophets", "Ezekiel"),
    ("Prophets", "Hosea"),
    ("Prophets", "Joel"),
    ("Prophets", "Amos"),
    ("Prophets", "Obadiah"),
    ("Prophets", "Jonah"),
    ("Prophets", "Micah"),
    ("Prophets", "Nahum"),
    ("Prophets", "Habakkuk"),
    ("Prophets", "Zephaniah"),
    ("Prophets", "Haggai"),
    ("Prophets", "Zechariah"),
    ("Prophets", "Malachi"),
    ("Writings", "Psalms"),
    ("Writings", "Proverbs"),
    ("Writings", "Job"),
    ("Writings", "Song of Songs"),
    ("Writings", "Ruth"),
    ("Writings", "Lamentations"),
    ("Writings", "Ecclesiastes"),
    ("Writings", "Esther"),
    ("Writings", "Daniel"),
    ("Writings", "Ezra"),
    ("Writings", "Nehemiah"),
    ("Writings", "I Chronicles"),
    ("Writings", "II Chronicles"),
]

# Hebrew names for the three sections of the Tanakh.
SECTION_HE = {"Torah": "תורה", "Prophets": "נביאים", "Writings": "כתובים"}


# --- Text cleaning -----------------------------------------------------------
#
# The Sefaria/tanach.us text carries editorial apparatus alongside the verse
# itself. Left in place it corrupts the letter matching that this whole app is
# built on, so it is removed here, once, at build time:
#
#   (פ) / (ס)   petucha and setuma markers, which sit *after* the sof pasuq.
#               3,124 verses carry one, and because פ and ס are Hebrew letters
#               they would otherwise be read as the verse's final letter --
#               silently breaking the primary search for 13% of the corpus.
#   [קרי]       ketiv/qere. The unpointed ketiv is followed by the pointed qere
#               in brackets. The qere is the text as it is *read*, and reading
#               is what this app is for, so the qere is kept and the ketiv
#               dropped. This corrects the first letter of 16 verses.
#   <br><small> two verses (Lamentations 5:22, Ecclesiastes 12:14) append the
#               penultimate verse, per the custom of not ending on a harsh note.
#   U+200D      a zero-width joiner used for special letter forms, which would
#               otherwise split the word around it into two.

HTML_TAIL = re.compile(r"<.*", re.DOTALL)
ZERO_WIDTH = re.compile(r"[\u200d\u200c]")
# Ketiv/qere. The export writes the unpointed ketiv, then the pointed qere in
# brackets: "מנ הסערה [מִן ׀] [הַסְּעָרָה]". The two runs can differ in length --
# two ketiv words may be read as one, or one as two -- so the rule is "a run of
# unpointed tokens followed by a run of bracketed groups", not a 1:1 swap. The
# qere is the text as it is read, and reading is what this app is for, so the
# qere is kept and the ketiv dropped.
#
# A bare token must begin at a boundary (start of text, whitespace, or maqaf),
# never in the middle of a pointed word -- the lookbehind below excludes every
# Hebrew letter and mark except maqaf (U+05BE), which does join a ketiv to the
# word before it ("אֲשֶׁר־המפרוצים").
BOUNDARY = r"(?<![\u05d0-\u05ea\u0591-\u05bd\u05bf-\u05c7])"
UNPOINTED = r"[\u05d0-\u05ea]+\u05be?"
QERE_GROUP = r"\[[^\]]*\]"
KETIV_QERE = re.compile(
    BOUNDARY + r"(?:" + UNPOINTED + r"\s+)*" + UNPOINTED + r"\s*((?:" + QERE_GROUP + r"\s*)+)"
)
BRACKETS = re.compile(r"[\[\]]")

# Ketiv velo qere: written in the text but not read aloud, and given no qere at
# all (Ruth 3:12 "אם", Jeremiah 39:12 "אם"). Anything still unpointed once the
# qere substitution above has run is one of these, and is dropped.
KETIV_ONLY = re.compile(BOUNDARY + r"[\u05d0-\u05ea]+(?=\s|$)")

# (פ) petucha, (ס) setuma, and (׆) nun hafukha.
PARASHA_MARKER = re.compile(r"[(\{]\s*[\u05e4\u05e1\u05e9\u05c6]{1,2}\s*[)\}]")
WHITESPACE = re.compile(r"\s+")


def clean_verse(text: str) -> str:
    """Reduce a raw export verse to the text as it is read aloud."""
    text = HTML_TAIL.sub("", text)          # drop appended repeated verses
    text = ZERO_WIDTH.sub("", text)
    text = KETIV_QERE.sub(lambda m: BRACKETS.sub("", m.group(1)), text)
    text = KETIV_ONLY.sub("", text)
    # Qere velo ketiv: read but not written, so it appears bracketed with no
    # ketiv before it (Ruth 3:5 "[אֵלַי]"). The words are read -- keep them and
    # drop only the brackets.
    text = BRACKETS.sub("", text)
    text = PARASHA_MARKER.sub("", text)     # drop (פ) / (ס)
    return WHITESPACE.sub(" ", text).strip()


def book_url(section: str, book: str) -> str:
    """Build the export URL for one book, quoting spaces and the apostrophe."""
    path = f"{section}/{book}/Hebrew/{VERSION_FILE}"
    return f"{BUCKET}/{urllib.parse.quote(path)}"


def fetch_book(entry: tuple[int, tuple[str, str]]) -> dict:
    """Download and shape a single book. Returns a dict ready for the dataset."""
    order, (section, book) = entry
    url = book_url(section, book)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        raise SystemExit(f"failed to fetch {book}: HTTP {exc.code} for {url}") from exc

    # Sefaria stores the text as text[chapter_index][verse_index]. Drop empty
    # verses (the export pads a few chapters) but keep the verse numbering that
    # the surviving verses imply, so references stay correct.
    chapters: list[list[str]] = []
    for chapter in raw["text"]:
        cleaned = (clean_verse(verse) for verse in chapter if verse)
        chapters.append([verse for verse in cleaned if verse])

    verse_count = sum(len(chapter) for chapter in chapters)
    print(f"  {book:<16} {verse_count:>5} verses", file=sys.stderr)

    return {
        "order": order,
        "he": raw["heTitle"],
        "en": raw["title"],
        "section": section,
        "sectionHe": SECTION_HE[section],
        "chapters": chapters,
    }


def main() -> int:
    print(f"Fetching {len(BOOKS)} book files from Sefaria's export bucket…", file=sys.stderr)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        books = list(pool.map(fetch_book, enumerate(BOOKS)))

    # Threads finish out of order; restore canonical order before writing.
    books.sort(key=lambda b: b["order"])
    for book in books:
        del book["order"]

    verse_count = sum(len(ch) for b in books for ch in b["chapters"])
    dataset = {
        "source": "https://github.com/Sefaria/Sefaria-Export",
        "version": VERSION_FILE.removesuffix(".json"),
        "textSource": "http://www.tanach.us/Tanach.xml",
        "license": "Public Domain",
        "bookCount": len(books),
        "verseCount": verse_count,
        "books": books,
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dataset, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.open(DATA_PATH, "wb", compresslevel=9) as handle:
        handle.write(payload)

    size_mb = DATA_PATH.stat().st_size / 1024 / 1024
    print(
        f"\nWrote {DATA_PATH.relative_to(Path.cwd())}: "
        f"{len(books)} books, {verse_count:,} verses, {size_mb:.2f} MB gzipped",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
