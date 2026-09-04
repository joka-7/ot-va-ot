"""Loading and indexing the Tanakh corpus.

The corpus lives in ``data/tanakh.json.gz``, committed to the repository and
built by ``scripts/build_dataset.py``. It is read once at process start, kept in
memory, and never refetched — the running application makes no network calls.
"""

from __future__ import annotations

import functools
import gzip
import json
from pathlib import Path

from .hebrew import he_number, normalize, words

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "tanakh.json.gz"


class Verse:
    """A single verse, with its normalized forms precomputed.

    ``index`` is the verse's position in the whole corpus, in canonical order.
    Two verses are adjacent when their indexes differ by one *and* they share a
    ``book_index`` — which lets a pair span a chapter boundary (genuinely the
    next verse) while never spanning the seam between two books.
    """

    __slots__ = (
        "index", "book_index", "book", "book_en", "book_fr", "section",
        "chapter", "number", "text", "ref", "chapter_he", "verse_he",
        "letters", "first", "last", "word_list", "word_set",
    )

    def __init__(
        self,
        index: int,
        book_index: int,
        book: str,
        book_en: str,
        book_fr: str,
        section: str,
        chapter: int,
        number: int,
        text: str,
    ):
        self.index = index
        self.book_index = book_index
        self.book = book
        self.book_en = book_en
        self.book_fr = book_fr
        self.section = section
        self.chapter = chapter
        self.number = number
        self.text = text
        # Gematria forms, precomputed once: the Hebrew-locale UI shows these
        # rather than Arabic numerals, and the traditional citation format
        # (used for copy-to-clipboard) always uses them regardless of locale.
        self.chapter_he = he_number(chapter)
        self.verse_he = he_number(number)
        self.ref = f"{book} {self.chapter_he}:{self.verse_he}"

        # Normalized forms, computed once at startup so that searching is cheap.
        self.letters = normalize(text)
        self.first = self.letters[0] if self.letters else ""
        self.last = self.letters[-1] if self.letters else ""
        self.word_list = tuple(words(text))
        self.word_set = frozenset(self.word_list)


class Corpus:
    """The full Tanakh plus the indexes the search relies on."""

    def __init__(self, dataset: dict):
        self.source: str = dataset["source"]
        self.version: str = dataset["version"]
        self.license: str = dataset["license"]

        self.verses: list[Verse] = []
        self.books: list[dict] = []

        for book_index, book in enumerate(dataset["books"]):
            self.books.append(
                {
                    "he": book["he"],
                    "en": book["en"],
                    "fr": book["fr"],
                    "section": book["sectionHe"],
                }
            )
            for chapter_number, chapter in enumerate(book["chapters"], start=1):
                for verse_number, text in enumerate(chapter, start=1):
                    self.verses.append(
                        Verse(
                            index=len(self.verses),
                            book_index=book_index,
                            book=book["he"],
                            book_en=book["en"],
                            book_fr=book["fr"],
                            section=book["sectionHe"],
                            chapter=chapter_number,
                            number=verse_number,
                            text=text,
                        )
                    )

        # Index 1: verses grouped by their (first letter, last letter) pair.
        # This is the primary custom, so it must be an O(1) lookup.
        self.by_letter_pair: dict[tuple[str, str], list[int]] = {}
        # Index 2: verses containing a given word, for exact-word name matches.
        self.by_word: dict[str, list[int]] = {}

        for verse in self.verses:
            if verse.letters:
                self.by_letter_pair.setdefault((verse.first, verse.last), []).append(verse.index)
            for word in verse.word_set:
                self.by_word.setdefault(word, []).append(verse.index)

    def __len__(self) -> int:
        return len(self.verses)

    def letter_matches(self, first: str, last: str) -> list[int]:
        """Verse indexes whose first and last letters match the given pair."""
        return self.by_letter_pair.get((first, last), [])

    def exact_word_matches(self, name: str) -> list[int]:
        """Verse indexes containing ``name`` as a standalone word."""
        return self.by_word.get(name, [])

    def partial_word_matches(self, name: str) -> list[int]:
        """Verse indexes where ``name`` appears inside a longer word.

        Covers attached prefixes (ו, ה, ב, כ, ל, מ, ש) and suffixes. Verses that
        already contain the name as a standalone word are excluded, so the two
        tiers never overlap. A linear scan is fast enough here — roughly 230k
        short substring checks, a few milliseconds — and avoids carrying a
        suffix index for a secondary result group.
        """
        exact = set(self.exact_word_matches(name))
        return [
            verse.index
            for verse in self.verses
            if verse.index not in exact and any(name in word for word in verse.word_set)
        ]

    def neighbour(self, verse: Verse, offset: int) -> Verse | None:
        """The verse ``offset`` positions away, if it is in the same book."""
        target = verse.index + offset
        if not 0 <= target < len(self.verses):
            return None
        candidate = self.verses[target]
        return candidate if candidate.book_index == verse.book_index else None


@functools.lru_cache(maxsize=1)
def load_corpus(path: Path | None = None) -> Corpus:
    """Load and index the corpus. Cached, so this only happens once per process."""
    with gzip.open(path or DATA_PATH, "rt", encoding="utf-8") as handle:
        return Corpus(json.load(handle))
