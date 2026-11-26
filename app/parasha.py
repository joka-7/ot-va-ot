"""The weekly portion split into seven days, for reading it twice with Targum.

A week runs from Saturday (day 1, ראשון) to Friday (day 7, שביעי) and studies the
portion read on the Shabbat that ends it. The portion's verses are cut into seven
runs as equal in words as whole verses allow; these are not the traditional aliyot,
which differ in length.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache
from pathlib import Path

from pyluach import dates, parshios

from .corpus import Corpus, Verse
from .hebrew import he_number
from .search import Payload

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "parashot.json"
DAYS_IN_WEEK = 7
SATURDAY = 5  # date.weekday()
MAX_SHABBATOT_AHEAD = 4  # holiday weeks can have no portion; a few Shabbatot are always enough


class ParashaError(LookupError):
    """A week that cannot be planned; ``code`` is the stable API error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Portion:
    """One weekly portion: its names and its first and last verse as (chapter, verse)."""

    he: str
    en: str
    book: str
    start: tuple[int, int]
    end: tuple[int, int]


@dataclass(frozen=True)
class DayPart:
    """The verses read on one day, from ``start`` to ``end`` inclusive."""

    day: int
    date: date
    book: str
    start: tuple[int, int]
    end: tuple[int, int]
    words: int

    def as_dict(self) -> Payload:
        """The JSON shape of one entry of ``days`` in ``GET /api/parasha``."""
        return {
            "day": self.day,
            "date": self.date.isoformat(),
            "book": self.book,
            "start": _verse_dict(self.start),
            "end": _verse_dict(self.end),
            "words": self.words,
        }


@dataclass(frozen=True)
class WeekPlan:
    """The portion(s) of a week and its seven day parts."""

    week_start: date
    read_on: date
    portions: tuple[Portion, ...]
    days: tuple[DayPart, ...]

    def as_dict(self) -> Payload:
        """The JSON shape of ``GET /api/parasha``."""
        return {
            "weekStart": self.week_start.isoformat(),
            "readOn": self.read_on.isoformat(),
            "portions": [{"he": p.he, "en": p.en} for p in self.portions],
            "days": [day.as_dict() for day in self.days],
        }


def _verse_dict(verse: tuple[int, int]) -> Payload:
    chapter, number = verse
    return {
        "chapter": chapter,
        "verse": number,
        "chapterHe": he_number(chapter),
        "verseHe": he_number(number),
    }


@cache
def load_portions() -> tuple[Portion, ...]:
    """The 54 portions in reading order, from ``data/parashot.json``."""
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return tuple(
        Portion(
            he=item["he"],
            en=item["en"],
            book=item["book"],
            start=(item["start"][0], item["start"][1]),
            end=(item["end"][0], item["end"][1]),
        )
        for item in raw
    )


def week_start(day: date) -> date:
    """The Saturday on or before ``day``, the first day of its week."""
    return day - timedelta(days=(day.weekday() - SATURDAY) % 7)


def portions_read_on(shabbat: date, israel: bool) -> tuple[Portion, ...]:
    """The portion(s) read on a Shabbat, or none when it falls on a holiday."""
    heb_day = dates.GregorianDate(shabbat.year, shabbat.month, shabbat.day)
    found = parshios.getparsha(heb_day, israel)
    portions = load_portions()
    return tuple(portions[index] for index in found or ())


def split_by_words(word_counts: Sequence[int], parts: int = DAYS_IN_WEEK) -> list[tuple[int, int]]:
    """Cut a run of verses into ``parts`` runs as equal in words as whole verses allow.

    Args:
        word_counts: The number of words in each verse, in order.
        parts: How many runs to make.

    Returns:
        ``parts`` ``(first, last)`` verse positions, inclusive, covering every verse
        once and in order, each cut at the verse boundary nearest its even share.

    Raises:
        ValueError: If there are fewer verses than parts.
    """
    verses = len(word_counts)
    if verses < parts:
        raise ValueError(f"{verses} verses cannot make {parts} parts")
    total = sum(word_counts)
    running = [0]
    for count in word_counts:
        running.append(running[-1] + count)

    cuts: list[int] = []  # a cut at i ends a part after the verse at position i - 1
    for part in range(1, parts):
        target = total * part / parts
        lowest = (cuts[-1] if cuts else 0) + 1
        highest = verses - (parts - part)
        cuts.append(min(range(lowest, highest + 1), key=lambda i: abs(running[i] - target)))
    bounds = [0, *cuts, verses]
    return [(bounds[i], bounds[i + 1] - 1) for i in range(parts)]


def week_plan(corpus: Corpus, day: date, israel: bool) -> WeekPlan:
    """Plan the week that contains ``day``.

    The week studies the portion read on its closing Shabbat. If that Shabbat has no
    portion (a holiday), the next Shabbat that has one is used.

    Args:
        corpus: The loaded Tanakh.
        day: Any date in the week.
        israel: Whether to follow the Israeli reading schedule.

    Raises:
        ParashaError: With code ``no_portion`` if no portion is found within a few weeks.
    """
    start = week_start(day)
    for weeks_ahead in range(MAX_SHABBATOT_AHEAD):
        shabbat = start + timedelta(days=DAYS_IN_WEEK + 7 * weeks_ahead)
        portions = portions_read_on(shabbat, israel)
        if portions:
            break
    else:
        raise ParashaError("no_portion")

    verses = _verses_between(corpus, portions[0], portions[-1])
    ranges = split_by_words([len(verse.word_list) for verse in verses], DAYS_IN_WEEK)
    days = tuple(
        DayPart(
            day=number,
            date=start + timedelta(days=number - 1),
            book=portions[0].book,
            start=(verses[first].chapter, verses[first].number),
            end=(verses[last].chapter, verses[last].number),
            words=sum(len(verse.word_list) for verse in verses[first : last + 1]),
        )
        for number, (first, last) in enumerate(ranges, start=1)
    )
    return WeekPlan(week_start=start, read_on=shabbat, portions=portions, days=days)


def _verses_between(corpus: Corpus, first: Portion, last: Portion) -> list[Verse]:
    book_index = next(i for i, book in enumerate(corpus.books) if book["he"] == first.book)
    in_book = [verse for verse in corpus.verses if verse.book_index == book_index]
    keys = [(verse.chapter, verse.number) for verse in in_book]
    return in_book[keys.index(first.start) : keys.index(last.end) + 1]
