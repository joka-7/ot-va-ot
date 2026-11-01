"""Free-text search: a word or phrase anywhere in the Tanakh.

Separate from ``search.py`` on purpose. That module answers "which verses fit
this *name*", where a comma means "another name"; here the input is ordinary
text, so a comma is just punctuation and nothing about name matching applies.

A query is one or more words, matched in one of two ways:

* **ordered** (the default) -- the words must appear next to each other, in
  that order, inside one verse. Maqaf splits words, so ``על פני`` finds
  ``עַל־פְּנֵי``.
* **anywhere** -- every word must appear somewhere in the verse, in any order.

Results come in two tiers that never overlap, mirroring the name search: verses
where each query word is a whole word, and verses where the words only occur
*inside* longer words (attached prefixes and suffixes such as ``וַ`` or ``ים``).

Niqqud is optional. A query word typed without vowels matches the word however
it is pointed; a word typed *with* vowels must match the verse's vowels too.
Cantillation marks are never compared, so a query pasted from a printed text
still matches.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from .corpus import Corpus, Verse
from .hebrew import mark_end, normalize_finals, word_spans, words
from .search import DEFAULT_LIMIT, MAX_LIMIT, Highlight, Payload, serialize

# A single letter would match nearly every verse, which is noise, not a search.
MIN_LETTERS = 2
MAX_WORDS = 12
MAX_QUERY_LENGTH = 200

# Cantillation, meteg, paseq, sof pasuq and the two marks above/below: present
# in the text, never part of a comparison. Maqaf (U+05BE) is deliberately not
# here -- it separates words.
_ACCENTS = re.compile("[֑-ֽ֯׀׃-ׅ]")

# What remains once accents are gone: vowels, dagesh, rafe, shin/sin dot and
# qamats qatan.
_POINT_CHARS = "ְ-ׇּֿׁׂ"
_NIQQUD = re.compile(f"[{_POINT_CHARS}]")
_NOT_POINTED_WORD = re.compile(f"[^א-ת{_POINT_CHARS}]+")


class InvalidPhrase(ValueError):
    """A query that cannot be searched; ``code`` is the stable API error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _canonical(word: str) -> str:
    """NFC puts the marks on a letter in one canonical order, then finals fold."""
    return normalize_finals(unicodedata.normalize("NFC", word))


def pointed_words(text: str) -> tuple[str, ...]:
    """Split ``text`` into words that keep their niqqud but not their accents.

    Word boundaries match :func:`app.hebrew.words`, so the n-th pointed word is
    the pointed form of the n-th plain word.
    """
    stripped = _ACCENTS.sub("", text)
    return tuple(_canonical(word) for word in _NOT_POINTED_WORD.split(stripped) if word)


@functools.lru_cache(maxsize=1)
def _pointed_index(corpus: Corpus) -> tuple[tuple[str, ...], ...]:
    """Pointed words for every verse, built on the first niqqud search only.

    Roughly half a second of work that a search without vowels never needs, so
    it is not paid at boot.
    """
    return tuple(pointed_words(verse.text) for verse in corpus.verses)


@dataclass(frozen=True)
class QueryWord:
    """One word of the query; ``pointed`` is None when it was typed without niqqud."""

    plain: str
    pointed: str | None


@dataclass(frozen=True)
class PhraseQuery:
    """A validated text query."""

    raw: str
    words: tuple[QueryWord, ...]
    ordered: bool

    @property
    def uses_niqqud(self) -> bool:
        return any(word.pointed is not None for word in self.words)

    @classmethod
    def parse(cls, raw: str, ordered: bool = True) -> PhraseQuery:
        """Validate and normalize a query.

        Args:
            raw: The text the user typed.
            ordered: True for consecutive words in order, False for anywhere.

        Raises:
            InvalidPhrase: when the text is empty, has no Hebrew, is too short
                to be a meaningful search, or is too long.
        """
        text = raw.strip()
        if not text:
            raise InvalidPhrase("empty_text")
        if len(text) > MAX_QUERY_LENGTH:
            raise InvalidPhrase("too_long")

        plain = words(text)
        if not plain:
            raise InvalidPhrase("invalid_phrase")
        if len(plain) > MAX_WORDS:
            raise InvalidPhrase("too_long")
        if sum(len(word) for word in plain) < MIN_LETTERS:
            raise InvalidPhrase("too_short")

        return cls(
            raw=text,
            words=tuple(
                QueryWord(p, q if _NIQQUD.search(q) else None)
                for p, q in zip(plain, pointed_words(text), strict=True)
            ),
            ordered=ordered,
        )


def _word_matches(spec: QueryWord, plain: str, pointed: str, partial: bool) -> bool:
    """Whether one verse word satisfies one query word."""
    if spec.pointed is None:
        return spec.plain in plain if partial else spec.plain == plain
    return spec.pointed in pointed if partial else spec.pointed == pointed


def matched_word_indexes(
    query: PhraseQuery,
    plain: Sequence[str],
    pointed: Sequence[str],
    partial: bool,
) -> list[int]:
    """Positions of the verse words that satisfy the query, or ``[]`` for no match.

    Args:
        query: The validated query.
        plain: The verse's words, letters only.
        pointed: The same words with niqqud (index-aligned with ``plain``).
        partial: Match query words inside longer words rather than whole.
    """
    length = len(query.words)

    def hit(spec: QueryWord, at: int) -> bool:
        return _word_matches(spec, plain[at], pointed[at], partial)

    if query.ordered:
        matched: set[int] = set()
        for start in range(len(plain) - length + 1):
            if all(hit(spec, start + offset) for offset, spec in enumerate(query.words)):
                matched.update(range(start, start + length))
        return sorted(matched)

    per_word = [[at for at in range(len(plain)) if hit(spec, at)] for spec in query.words]
    if not all(per_word):
        return []
    return sorted({at for positions in per_word for at in positions})


def _highlights(
    verse: Verse,
    query: PhraseQuery,
    matched: list[int],
    pointed: Sequence[str],
    partial: bool,
) -> list[Highlight]:
    """Highlight the matched words -- or, for a partial match, just the part matched."""
    spans = word_spans(verse.text)
    highlights: list[Highlight] = []
    for at in matched:
        word = spans[at]
        needle = ""
        if partial:
            spec = next(
                s for s in query.words if _word_matches(s, verse.word_list[at], pointed[at], True)
            )
            # With niqqud the consonantal position can differ from the pointed
            # one, so the whole word is highlighted rather than a guessed part.
            needle = spec.plain if spec.pointed is None else ""
        span = word.span_of(needle) if needle else None
        if span:
            start, raw_end = span
            highlights.append(
                {"start": start, "end": mark_end(verse.text, raw_end - 1), "kind": "match"}
            )
        else:
            highlights.append({"start": word.start, "end": word.end, "kind": "match"})
    return highlights


def search_phrase(corpus: Corpus, query: PhraseQuery, limit: int = DEFAULT_LIMIT) -> Payload:
    """Find the verses containing the query, in an exact tier and a partial tier."""
    limit = max(1, min(limit, MAX_LIMIT))
    pointed_index = _pointed_index(corpus) if query.uses_niqqud else None

    # Every query word must occur as a substring of the verse's letters for any
    # kind of match to be possible: cheap, and it discards almost every verse
    # before the precise comparison below.
    plain_forms = [word.plain for word in query.words]
    candidates = [v for v in corpus.verses if all(form in v.letters for form in plain_forms)]

    exact_found: list[tuple[Verse, list[int]]] = []
    partial_found: list[tuple[Verse, list[int]]] = []
    for verse in candidates:
        # Without niqqud in the query no word is compared pointed, so the plain
        # words stand in and the pointed index is never built.
        pointed = pointed_index[verse.index] if pointed_index else verse.word_list
        whole = matched_word_indexes(query, verse.word_list, pointed, partial=False)
        if whole:
            exact_found.append((verse, whole))
            continue
        inside = matched_word_indexes(query, verse.word_list, pointed, partial=True)
        if inside:
            partial_found.append((verse, inside))

    def group(found: list[tuple[Verse, list[int]]], is_partial: bool) -> Payload:
        return {
            "total": len(found),
            "verses": [
                serialize(
                    verse,
                    _highlights(
                        verse,
                        query,
                        matched,
                        pointed_index[verse.index] if pointed_index else verse.word_list,
                        is_partial,
                    ),
                )
                for verse, matched in found[:limit]
            ],
        }

    return {
        "query": {
            "text": query.raw,
            "words": len(query.words),
            "ordered": query.ordered,
            "niqqud": query.uses_niqqud,
        },
        "exact": group(exact_found, False),
        "partial": group(partial_found, True),
    }
