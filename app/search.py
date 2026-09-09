"""Verse matching.

Three kinds of search, all of them working on the normalized forms that
``Verse`` precomputes at startup:

1. **Letter match** — the primary Jewish custom: the verse begins with the
   name's first letter and ends with its last letter. A name with no comma
   but more than one word (e.g. "אסתר מלכה") is one compound name here: its
   first letter is the first letter of its first word, its last letter the
   last letter of its last word, since whitespace is stripped before the
   comparison -- exactly the traditional reading of a multi-word name.
2. **Name in verse** — the name appears in the text, in two tiers so that clean
   matches lead and noisy ones stay clearly separated.
3. **Pairs** — for two or three names (each name separated by a comma),
   consecutive verses matching one name then another, which is the
   traditional find for a couple. With three names, every combination of two
   of them is checked, since a full three-way consecutive run is vanishingly
   rare on top of an already-rare pair.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from .corpus import Corpus, Verse
from .hebrew import first_last, has_hebrew, letter_positions, mark_end, normalize, word_spans

# How many verses a single result group returns by default. The true total is
# always reported alongside, so the client can say "showing 100 of 259".
DEFAULT_LIMIT = 100
MAX_LIMIT = 500

# One name, or up to this many separated by commas.
MAX_NAMES = 3

# Pairs are rare enough that returning all of them is never a problem.
PAIR_LIMIT = 50


@dataclass
class Name:
    """A parsed search term."""

    raw: str
    normalized: str
    first: str
    last: str

    @classmethod
    def parse(cls, raw: str) -> "Name":
        text = raw.strip()
        if not has_hebrew(text):
            raise ValueError(f"'{raw}' does not contain Hebrew letters")
        first, last = first_last(text)
        return cls(raw=text, normalized=normalize(text), first=first, last=last)

    def matches_letters(self, verse: Verse) -> bool:
        """True if the verse opens and closes with this name's letters."""
        return bool(verse.letters) and verse.first == self.first and verse.last == self.last


# --- Highlighting ------------------------------------------------------------


def letter_highlights(verse: Verse) -> list[dict]:
    """Highlight the verse's first and last letters, marks included."""
    positions = letter_positions(verse.text)
    if not positions:
        return []
    first, last = positions[0], positions[-1]
    highlights = [{"start": first, "end": mark_end(verse.text, first), "kind": "first"}]
    if last != first:
        highlights.append({"start": last, "end": mark_end(verse.text, last), "kind": "last"})
    return highlights


def name_highlights(verse: Verse, name: Name) -> list[dict]:
    """Highlight every occurrence of the name inside the verse."""
    highlights = []
    for word in word_spans(verse.text):
        span = word.span_of(name.normalized)
        if span:
            start, raw_end = span
            highlights.append(
                {"start": start, "end": mark_end(verse.text, raw_end - 1), "kind": "name"}
            )
    return highlights


def serialize(verse: Verse, highlights: list[dict] | None = None) -> dict:
    """Shape a verse for the API.

    ``book`` carries all three languages so the client can label it without a
    second request; ``chapter``/``verse`` are plain integers for an English or
    French locale, and ``chapterHe``/``verseHe`` are the Hebrew gematria used
    in the Hebrew locale and in ``ref`` -- the traditional citation form,
    which stays in Hebrew regardless of the UI language, same as the verse
    text itself.
    """
    return {
        "book": {"he": verse.book, "en": verse.book_en, "fr": verse.book_fr},
        "section": verse.section,
        "chapter": verse.chapter,
        "verse": verse.number,
        "chapterHe": verse.chapter_he,
        "verseHe": verse.verse_he,
        "ref": verse.ref,
        "text": verse.text,
        "highlights": sorted(highlights or [], key=lambda h: h["start"]),
        # Rashi's commentary, pre-cleaned HTML limited to <b>/<small>/<br> (see
        # scripts/build_dataset.py) -- empty when he wrote nothing on this verse.
        "rashi": verse.rashi,
    }


# --- Single-name search ------------------------------------------------------


def search_name(corpus: Corpus, name: Name, limit: int) -> dict:
    """Run all single-name searches for one name."""
    letter_ids = corpus.letter_matches(name.first, name.last)
    exact_ids = corpus.exact_word_matches(name.normalized)
    partial_ids = corpus.partial_word_matches(name.normalized)

    def group(ids: list[int], highlighter) -> dict:
        """A result group: the verses shown, plus how many exist in total."""
        shown = [corpus.verses[i] for i in ids[:limit]]
        return {
            "total": len(ids),
            "verses": [serialize(v, highlighter(v)) for v in shown],
        }

    return {
        "name": name.raw,
        "first": name.first,
        "last": name.last,
        "letterMatch": group(letter_ids, letter_highlights),
        "exactWord": group(exact_ids, lambda v: name_highlights(v, name)),
        "partialWord": group(partial_ids, lambda v: name_highlights(v, name)),
    }


# --- Pair (consecutive-verse) search ----------------------------------------


def find_pairs(corpus: Corpus, first_name: Name, second_name: Name, gap: int) -> list[dict]:
    """Find verse N matching ``first_name`` and verse N+gap matching ``second_name``.

    ``gap`` of 1 means strictly consecutive verses; 2 leaves one verse between
    them. Both verses must belong to the same book, but they may sit in
    different chapters — the last verse of a chapter and the first of the next
    really are consecutive verses.
    """
    results = []
    for verse in corpus.verses:
        if not first_name.matches_letters(verse):
            continue
        partner = corpus.neighbour(verse, gap)
        if partner is None or not second_name.matches_letters(partner):
            continue
        results.append(
            {
                "first": serialize(verse, letter_highlights(verse)),
                "second": serialize(partner, letter_highlights(partner)),
                "firstName": first_name.raw,
                "secondName": second_name.raw,
                "crossesChapter": verse.chapter != partner.chapter,
            }
        )
        if len(results) >= PAIR_LIMIT:
            break
    return results


def build_pair_group(corpus: Corpus, name_a: Name, name_b: Name) -> dict:
    """All pair-based results between two of the search's names."""
    return {
        "names": [name_a.raw, name_b.raw],
        "consecutive": find_pairs(corpus, name_a, name_b, gap=1),
        "reversed": find_pairs(corpus, name_b, name_a, gap=1),
        "nearMiss": find_pairs(corpus, name_a, name_b, gap=2),
    }


def search_multi(corpus: Corpus, names: list[Name]) -> list[dict]:
    """A pair group for every unique combination of two of the given names.

    Two names -> one combination. Three names -> three (each possible duo).
    """
    return [
        build_pair_group(corpus, names[i], names[j])
        for i, j in itertools.combinations(range(len(names)), 2)
    ]


# --- Entry point -------------------------------------------------------------


def search(corpus: Corpus, names: list[Name], limit: int = DEFAULT_LIMIT) -> dict:
    """Run the full search for one, two, or three names."""
    limit = max(1, min(limit, MAX_LIMIT))
    result = {
        "query": {"names": [n.raw for n in names], "mode": "single" if len(names) == 1 else "multi"},
        "names": [search_name(corpus, name, limit) for name in names],
    }
    if len(names) >= 2:
        result["pairs"] = search_multi(corpus, names)
    return result
