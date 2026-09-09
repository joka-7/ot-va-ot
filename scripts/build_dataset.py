#!/usr/bin/env python3
"""Build the local Tanakh dataset used by the app.

Downloads the 39 Hebrew book files of the "Tanach with Ta'amei Hamikra" version
from Sefaria's public export bucket, plus Rashi's commentary aligned to those
same verses, and writes them into a single gzipped JSON file at
``data/tanakh.json.gz``.

This script is a *build-time* tool. Run it once (or whenever you want to refresh
the corpus); the resulting file is committed to the repository, and the running
application never touches the network.

    python scripts/build_dataset.py

Source : https://github.com/Sefaria/Sefaria-Export  (text originally from tanach.us)
License: Public Domain
"""

from __future__ import annotations

import concurrent.futures
import gzip
import json
import re
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

# French book names. Sefaria's export gives Hebrew and English titles but no
# French ones, so these are supplied here -- standard French Bible book names,
# keyed by the English title used in BOOKS above.
BOOK_NAMES_FR = {
    "Genesis": "Genèse", "Exodus": "Exode", "Leviticus": "Lévitique",
    "Numbers": "Nombres", "Deuteronomy": "Deutéronome", "Joshua": "Josué",
    "Judges": "Juges", "I Samuel": "I Samuel", "II Samuel": "II Samuel",
    "I Kings": "I Rois", "II Kings": "II Rois", "Isaiah": "Ésaïe",
    "Jeremiah": "Jérémie", "Ezekiel": "Ézéchiel", "Hosea": "Osée",
    "Joel": "Joël", "Amos": "Amos", "Obadiah": "Abdias", "Jonah": "Jonas",
    "Micah": "Michée", "Nahum": "Nahoum", "Habakkuk": "Habacuc",
    "Zephaniah": "Sophonie", "Haggai": "Aggée", "Zechariah": "Zacharie",
    "Malachi": "Malachie", "Psalms": "Psaumes", "Proverbs": "Proverbes",
    "Job": "Job", "Song of Songs": "Cantique des Cantiques", "Ruth": "Ruth",
    "Lamentations": "Lamentations", "Ecclesiastes": "Ecclésiaste",
    "Esther": "Esther", "Daniel": "Daniel", "Ezra": "Esdras",
    "Nehemiah": "Néhémie", "I Chronicles": "I Chroniques",
    "II Chronicles": "II Chroniques",
}


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


# --- Rashi -------------------------------------------------------------------
#
# Rashi's commentary is fetched separately, from the same export bucket, and
# matched up to the verse it comments on. Each verse can carry zero, one, or
# several comments (one per phrase he addresses, each opening with the phrase
# in bold); they're joined into a single block, in order, the way a printed
# Mikraot Gedolot runs them.
#
# Sefaria's own markup for this is just <b> (the quoted phrase) and, rarely,
# <small> (an editorial aside, e.g. a variant-reading note). Anything else is
# stripped defensively -- this is the one piece of the dataset that ends up as
# innerHTML in the browser rather than plain text, so only that fixed,
# hand-verified tag set is ever allowed through.
RASHI_ROOT = "https://storage.googleapis.com/sefaria-export/json/Tanakh/Rishonim on Tanakh/Rashi"
RASHI_TAG = re.compile(r"<(?!/?(?:b|small|br)\b)[^>]*>", re.IGNORECASE)


def rashi_url(section: str, book: str) -> str:
    """Build the export URL for one book's merged Rashi text."""
    path = f"{section}/Rashi on {book}/Hebrew/merged.json"
    return f"{urllib.parse.quote(RASHI_ROOT, safe=':/')}/{urllib.parse.quote(path)}"


def clean_rashi_comment(text: str) -> str:
    """Reduce one raw Rashi comment to the safe HTML fragment the UI can show."""
    text = ZERO_WIDTH.sub("", text)
    text = RASHI_TAG.sub("", text)
    return WHITESPACE.sub(" ", text).strip()


def fetch_rashi(section: str, book: str) -> list[list[list[str]]] | None:
    """Download one book's Rashi text, shaped like Sefaria's export: a list of
    chapters, each a list of verses, each a list of that verse's comments.

    Returns ``None`` if this book has no Rashi at all (not expected for any of
    the 39 files today, but the corpus should still build if that changes).
    """
    url = rashi_url(section, book)
    # urlopen honours file:// and any custom scheme, so refuse anything but
    # https before opening it, same as fetch_book above.
    if not url.startswith("https://"):
        raise ValueError(f"refusing to fetch a non-https URL: {url}")
    try:
        with urllib.request.urlopen(url, timeout=120) as response:  # nosec B310 - scheme checked above
            return json.loads(response.read().decode("utf-8"))["text"]
    except urllib.error.HTTPError as exc:
        print(f"  warning: no Rashi for {book}: HTTP {exc.code}", file=sys.stderr)
        return None


def align_rashi(
    chapters: list[list[str]], rashi: list[list[list[str]]] | None, book: str
) -> list[list[str]]:
    """Line Rashi's comments up with ``chapters``, one joined block per verse.

    Sefaria trims trailing empty verses off the end of each chapter's array --
    a chapter whose last few verses draw no comment from Rashi is simply
    shorter here than the verse text's chapter -- so short chapters are padded
    back out with empty strings rather than treated as a mismatch.

    A chapter with *more* comments than verses is the opposite problem, and a
    real one: a few chapters of Rashi's commentary (Exodus 38, notably, in the
    Mishkan-construction chapters) are split against a different chapter
    boundary than this edition of the verse text uses, so position-by-position
    they'd land on the wrong verse entirely. Rather than risk that, such a
    chapter is skipped -- no Rashi shown is better than the wrong Rashi shown.
    """
    if rashi is None:
        return [[""] * len(chapter) for chapter in chapters]

    aligned = []
    for chapter_index, chapter in enumerate(chapters):
        rashi_chapter = rashi[chapter_index] if chapter_index < len(rashi) else []
        if len(rashi_chapter) > len(chapter):
            print(
                f"  warning: Rashi/{book} ch.{chapter_index + 1} has more comments "
                f"({len(rashi_chapter)}) than verses ({len(chapter)}) -- skipping",
                file=sys.stderr,
            )
            aligned.append([""] * len(chapter))
            continue

        joined = [
            " ".join(clean_rashi_comment(c) for c in comments if c.strip())
            for comments in rashi_chapter
        ]
        joined += [""] * (len(chapter) - len(joined))
        aligned.append(joined)
    return aligned


def book_url(section: str, book: str) -> str:
    """Build the export URL for one book, quoting spaces and the apostrophe."""
    path = f"{section}/{book}/Hebrew/{VERSION_FILE}"
    return f"{BUCKET}/{urllib.parse.quote(path)}"


def fetch_book(entry: tuple[int, tuple[str, str]]) -> dict:
    """Download and shape a single book. Returns a dict ready for the dataset."""
    order, (section, book) = entry
    url = book_url(section, book)
    # urlopen honours file:// and any custom scheme, so refuse anything but
    # https before opening it. The URL is built from the BUCKET constant today,
    # but that is a one-line edit away from not being true.
    if not url.startswith("https://"):
        raise ValueError(f"refusing to fetch a non-https URL: {url}")
    try:
        with urllib.request.urlopen(url, timeout=120) as response:  # nosec B310 - scheme checked above
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

    rashi = align_rashi(chapters, fetch_rashi(section, book), book)

    verse_count = sum(len(chapter) for chapter in chapters)
    rashi_count = sum(1 for chapter in rashi for verse in chapter if verse)
    print(f"  {book:<16} {verse_count:>5} verses, {rashi_count:>5} with Rashi", file=sys.stderr)

    return {
        "order": order,
        "he": raw["heTitle"],
        "en": raw["title"],
        "fr": BOOK_NAMES_FR[book],
        "section": section,
        "sectionHe": SECTION_HE[section],
        "chapters": chapters,
        "rashi": rashi,
    }


def main() -> int:
    missing = [book for _, book in BOOKS if book not in BOOK_NAMES_FR]
    if missing:
        raise SystemExit(f"BOOK_NAMES_FR is missing an entry for: {', '.join(missing)}")

    print(
        f"Fetching {len(BOOKS)} book files (text + Rashi) from Sefaria's export bucket…",
        file=sys.stderr,
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        books = list(pool.map(fetch_book, enumerate(BOOKS)))

    # Threads finish out of order; restore canonical order before writing.
    books.sort(key=lambda b: b["order"])
    for book in books:
        del book["order"]

    verse_count = sum(len(ch) for b in books for ch in b["chapters"])
    rashi_count = sum(1 for b in books for ch in b["rashi"] for verse in ch if verse)
    dataset = {
        "source": "https://github.com/Sefaria/Sefaria-Export",
        "version": VERSION_FILE.removesuffix(".json"),
        "textSource": "http://www.tanach.us/Tanach.xml",
        "rashiSource": "https://github.com/Sefaria/Sefaria-Export (Rashi, merged edition)",
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
        f"{len(books)} books, {verse_count:,} verses "
        f"({rashi_count:,} with Rashi), {size_mb:.2f} MB gzipped",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
