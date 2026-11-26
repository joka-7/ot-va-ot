#!/usr/bin/env python3
"""Build ``data/parashot.json``: where each of the 54 weekly portions starts and ends.

The ranges come from the ``Parasha`` alternate structure of Sefaria's schema for each
book of the Torah, taken as the first verse of the first aliyah and the last verse of
the last, so they follow the Tanakh text numbering Sefaria uses.

    python -m scripts.build_parashot

Source : https://github.com/Sefaria/Sefaria-Export
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

EXPORT = "https://storage.googleapis.com/sefaria-export/schemas"
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "parashot.json"
BOOKS = (
    ("Genesis", "בראשית"),
    ("Exodus", "שמות"),
    ("Leviticus", "ויקרא"),
    ("Numbers", "במדבר"),
    ("Deuteronomy", "דברים"),
)
REF = re.compile(
    r"^(?P<book>.+) (?P<chapter>\d+):(?P<verse>\d+)"
    r"(?:[-–](?:(?P<end_chapter>\d+):)?(?P<end_verse>\d+))?$"
)


def _fetch_schema(book_en: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{EXPORT}/{book_en}.json", timeout=30) as response:
        schema: dict[str, Any] = json.load(response)
    return schema


def _title(node: dict[str, Any], lang: str) -> str:
    return next(t["text"] for t in node["titles"] if t["lang"] == lang and t.get("primary"))


def _span(first_ref: str, last_ref: str) -> tuple[list[int], list[int]]:
    """The first verse of ``first_ref`` and the last verse of ``last_ref``, as [chapter, verse]."""
    first = REF.match(first_ref)
    last = REF.match(last_ref)
    if first is None or last is None:
        raise ValueError(f"unreadable aliyah reference: {first_ref!r} / {last_ref!r}")
    end_chapter = last["end_chapter"] or last["chapter"]
    end_verse = last["end_verse"] or last["verse"]
    return [int(first["chapter"]), int(first["verse"])], [int(end_chapter), int(end_verse)]


def build() -> list[dict[str, Any]]:
    """The 54 portions in reading order."""
    parashot: list[dict[str, Any]] = []
    for book_en, book_he in BOOKS:
        nodes = _fetch_schema(book_en)["alts"]["Parasha"]["nodes"]
        for node in nodes:
            start, end = _span(node["refs"][0], node["refs"][-1])
            parashot.append(
                {
                    "he": _title(node, "he"),
                    "en": _title(node, "en"),
                    "book": book_he,
                    "start": start,
                    "end": end,
                }
            )
    if len(parashot) != 54:
        raise ValueError(f"expected 54 portions, got {len(parashot)}")
    return parashot


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
