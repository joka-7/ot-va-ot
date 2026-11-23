"""Reading one chapter of the Tanakh: its verses, and the chapters on either side.

Search finds a verse; this serves the whole chapter around it so it can be read
straight through, with Rashi on the verses he wrote on.
"""

from __future__ import annotations

from dataclasses import dataclass

from .corpus import Corpus, Verse
from .hebrew import he_number
from .search import Payload


class ReaderError(LookupError):
    """A chapter that cannot be served; ``code`` is the stable API error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ChapterRef:
    """Where a chapter is: its book, by Hebrew name, and its number."""

    book: str
    chapter: int

    def as_dict(self) -> Payload:
        """The JSON shape of ``previous`` and ``next`` in ``GET /api/chapter``."""
        return {"book": self.book, "chapter": self.chapter}


@dataclass(frozen=True)
class ChapterPage:
    """One chapter, with where to go next and back."""

    book: dict[str, str]
    section: str
    chapter: int
    verses: list[Verse]
    previous: ChapterRef | None
    next: ChapterRef | None

    def as_dict(self) -> Payload:
        """The JSON shape of ``GET /api/chapter``."""
        chapter_he = he_number(self.chapter)
        return {
            "book": self.book,
            "section": self.section,
            "chapter": self.chapter,
            "chapterHe": chapter_he,
            "ref": f"{self.book['he']} {chapter_he}",
            "verses": [
                {
                    "verse": verse.number,
                    "verseHe": verse.verse_he,
                    "text": verse.text,
                    # Pre-cleaned HTML, limited to <b>/<small>/<br> at build time (see
                    # scripts/build_dataset.py); empty where Rashi wrote nothing.
                    "rashi": verse.rashi,
                }
                for verse in self.verses
            ],
            "previous": self.previous.as_dict() if self.previous else None,
            "next": self.next.as_dict() if self.next else None,
        }


def list_books(corpus: Corpus) -> list[Payload]:
    """The books and their chapter counts, for the reader's pickers.

    Args:
        corpus: The loaded Tanakh.

    Returns:
        One entry per book, in reading order: its names, section, ``chapters``
        count, and ``chaptersHe``, the Hebrew numeral of each chapter, so the
        client does not carry its own gematria.
    """
    return [
        {
            "he": book["he"],
            "en": book["en"],
            "fr": book["fr"],
            "section": book["section"],
            "chapters": book["chapters"],
            "chaptersHe": [he_number(number) for number in range(1, book["chapters"] + 1)],
        }
        for book in corpus.books
    ]


def chapter_page(corpus: Corpus, book_he: str, chapter: int) -> ChapterPage:
    """One chapter's verses and the chapters before and after it.

    Args:
        corpus: The loaded Tanakh.
        book_he: The book, by its Hebrew name.
        chapter: The chapter number, from 1.

    Returns:
        The chapter's verses in reading order. ``previous`` and ``next`` run on
        across a book boundary (the last chapter of Genesis leads to Exodus 1)
        and are ``None`` only at the very start and end of the Tanakh.

    Raises:
        ReaderError: With code ``unknown_book`` if there is no such book, or
            ``chapter_not_found`` if the book has no such chapter.
    """
    book_index = next((i for i, book in enumerate(corpus.books) if book["he"] == book_he), None)
    if book_index is None:
        raise ReaderError("unknown_book")
    span = corpus.chapter_spans.get((book_index, chapter))
    if span is None:
        raise ReaderError("chapter_not_found")

    order = corpus.chapter_order
    position = order.index((book_index, chapter))
    return ChapterPage(
        book={key: corpus.books[book_index][key] for key in ("he", "en", "fr")},
        section=corpus.books[book_index]["section"],
        chapter=chapter,
        verses=corpus.verses[span[0] : span[1]],
        previous=_ref(corpus, order[position - 1]) if position > 0 else None,
        next=_ref(corpus, order[position + 1]) if position + 1 < len(order) else None,
    )


def _ref(corpus: Corpus, chapter_key: tuple[int, int]) -> ChapterRef:
    book_index, chapter = chapter_key
    return ChapterRef(book=corpus.books[book_index]["he"], chapter=chapter)
