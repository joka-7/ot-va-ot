#!/usr/bin/env python3
"""Build the midrashim the reader shows under a verse of the Torah but never searches.

A midrash is not indexed by verse the way a commentary is, so it is lined up through
Sefaria's table of links: each link joins a passage of the midrash to the Torah verse it
explains. The links are streamed once (about 700 MB) and only the Torah rows of the chosen
midrashim are kept. Each is written as ``data/<id>.zip`` in the shape ``app/commentary.py``
reads for any commentary: a ``header.json`` and a member per book, one block per verse.

A midrash whose only versions are not under an allowed license is left out and reported,
not guessed at. A link over a range longer than ``MAX_LINKED_VERSES`` is skipped, since a
passage tied to a whole parasha explains none of its verses in particular.

    python -m scripts.build_midrashim                      # all, or --midrash mekhilta

Source : https://github.com/Sefaria/Sefaria-Export
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.hebrew import he_number
from scripts.build_commentaries import DATA_DIR, EXPORT, TANAKH_PATH, fetch_json, flatten
from scripts.build_dataset import clean_rashi_comment

LINK_FILES = 18
MAX_LINKED_VERSES = 5
MAX_PASSAGES_PER_VERSE = 6
MAX_PASSAGE_CHARS = 1500
TORAH_BOOKS = ("Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy")
TORAH_REF = re.compile(
    r"^(?P<book>[A-Za-z]+) (?P<chapter>\d+):(?P<verse>\d+)"
    r"(?:-(?:(?P<end_chapter>\d+):)?(?P<end_verse>\d+))?$"
)
CITATION_TAIL = re.compile(r"^ (?P<chapter>\d+)(?::(?P<segment>\d+))?(?:-.*)?$")

MEKHILTA_TRACTATES = {
    "Tractate Pischa": "פסחא",
    "Tractate Vayehi Beshalach": "ויהי בשלח",
    "Tractate Shirah": "שירתא",
    "Tractate Vayassa": "ויסע",
    "Tractate Amalek": "עמלק",
    "Tractate Bachodesh": "בחודש",
    "Tractate Nezikin": "נזיקין",
    "Tractate Kaspa": "כספא",
    "Tractate Shabbata": "שבתא",
}


@dataclass(frozen=True)
class MidrashSpec:
    """Where a midrash is in the export, and which licenses may be shown."""

    id: str
    toc_title: str  # its title in the table of contents
    he_title: str  # how a passage is headed
    allowed_licenses: frozenset[str]
    node_names: Mapping[str, str] | None = None  # English section key -> Hebrew, if sectioned


def _parasha_names() -> dict[str, str]:
    portions = json.loads((DATA_DIR / "parashot.json").read_text(encoding="utf-8"))
    names = {portion["en"]: portion["he"] for portion in portions}
    return {**names, **{f"Appendix to {en}": f"נספח {he}" for en, he in names.items()}}


SPECS: dict[str, MidrashSpec] = {
    spec.id: spec
    for spec in (
        # Beeri's edition is CC-BY-NC, the only version Sefaria has of it, as with Onkelos.
        MidrashSpec(
            "mekhilta",
            "Mekhilta DeRabbi Yishmael",
            "מכילתא דרבי ישמעאל",
            frozenset({"CC-BY-NC"}),
            MEKHILTA_TRACTATES,
        ),
        MidrashSpec(
            "tanchuma-buber",
            "Midrash Tanchuma Buber",
            "תנחומא בובר",
            frozenset({"Public Domain", "CC0"}),
            _parasha_names(),
        ),
        MidrashSpec(
            "sifrei-devarim",
            "Sifrei Devarim",
            "ספרי דברים",
            frozenset({"Public Domain", "CC0"}),
        ),
    )
}


def torah_links() -> Iterator[Link]:
    """Every link from a passage of a midrash to a verse of the Torah, from the export.

    Yields:
        ``(text title, passage citation, Torah reference)``, e.g.
        ``("Sifrei Devarim", "Sifrei Devarim 32:1", "Deuteronomy 10:20")``.
    """
    for number in range(LINK_FILES):
        print(f"  links{number}.csv", file=sys.stderr)
        with urllib.request.urlopen(  # nosec B310 - fixed https host
            f"{EXPORT}/links/links{number}.csv", timeout=300
        ) as response:
            for row in csv.reader(io.TextIOWrapper(response, encoding="utf-8")):
                if len(row) < 7:
                    continue
                first, second, _, title_1, title_2, category_1, category_2 = row[:7]
                for citation, torah, title, category, other in (
                    (first, second, title_1, category_1, category_2),
                    (second, first, title_2, category_2, category_1),
                ):
                    if category == "Midrash" and other == "Tanakh" and TORAH_REF.match(torah):
                        yield title, citation, torah


def verses_of(ref: str, verse_counts: Mapping[str, Sequence[int]]) -> list[tuple[str, int, int]]:
    """The ``(book, chapter, verse)`` of each verse a Torah reference covers.

    Returns an empty list for a range longer than ``MAX_LINKED_VERSES`` or one that does
    not lie inside the book.
    """
    match = TORAH_REF.match(ref)
    if match is None or match["book"] not in verse_counts:
        return []
    book = match["book"]
    counts = verse_counts[book]
    chapter, verse = int(match["chapter"]), int(match["verse"])
    end_chapter = int(match["end_chapter"] or chapter)
    end_verse = int(match["end_verse"] or verse)
    found: list[tuple[str, int, int]] = []
    while (chapter, verse) <= (end_chapter, end_verse):
        if chapter > len(counts):
            return []
        if verse > counts[chapter - 1]:
            chapter, verse = chapter + 1, 1
            continue
        found.append((book, chapter, verse))
        if len(found) > MAX_LINKED_VERSES:
            return []
        verse += 1
    return found


def shorten(text: str, limit: int = MAX_PASSAGE_CHARS) -> str:
    """``text`` cut at a word boundary within ``limit`` characters, with an ellipsis."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"


def passage_at(text: Any, node: str, chapter: int, segment: int | None) -> str | None:
    """One cleaned passage of a midrash, or ``None`` if the text has nothing there.

    Args:
        text: The version's ``text``: sections of chapters of segments, or chapters of
            segments for a midrash with no sections.
        node: The section's key, or ``""`` if the midrash has none.
        chapter: The chapter, from 1.
        segment: The segment, from 1, or ``None`` for the whole chapter.
    """
    body = text.get(node) if isinstance(text, dict) else text
    if not isinstance(body, list) or not 1 <= chapter <= len(body):
        return None
    chapter_text = body[chapter - 1]
    if segment is not None:
        chapter_text = chapter_text[segment - 1] if 1 <= segment <= len(chapter_text) else []
    pieces = [clean_rashi_comment(piece) for piece in flatten(chapter_text)]
    return " ".join(piece for piece in pieces if piece) or None


def chosen_text(spec: MidrashSpec) -> tuple[Any, str]:
    """The text and license of the allowed version with the most text, or ``SystemExit``."""
    toc = fetch_json(f"{EXPORT}/table_of_contents.json")
    leaf = next(leaf for leaf in _leaves(toc) if leaf.get("title") == spec.toc_title)
    path = urllib.parse.quote("/".join([*leaf["categories"], leaf["title"]]))
    base = f"{EXPORT}/json/{path}/Hebrew/"
    best: tuple[int, Any, str] | None = None
    for name, *_ in fetch_json(base + "merged.json")["versions"]:
        version = fetch_json(base + urllib.parse.quote(f"{name}.json"))
        if version.get("license") not in spec.allowed_licenses:
            continue
        size = len(json.dumps(version["text"], ensure_ascii=False))
        if best is None or size > best[0]:
            best = (size, version["text"], version["license"])
    if best is None:
        raise SystemExit(f"{spec.id}: no version under {sorted(spec.allowed_licenses)}")
    return best[1], best[2]


def _leaves(nodes: Any) -> Iterator[dict[str, Any]]:
    for node in nodes:
        if "contents" in node:
            yield from _leaves(node["contents"])
        else:
            yield node


def label(spec: MidrashSpec, node: str, chapter: int, segment: int | None) -> str:
    """The heading of a passage, e.g. ``תנחומא בובר בלק כ׳:א׳``."""
    parts = [spec.he_title]
    if node:
        parts.append((spec.node_names or {}).get(node, node))
    spot = he_number(chapter) + (f":{he_number(segment)}" if segment is not None else "")
    return " ".join([*parts, spot])


Link = tuple[str, str, str]  # (text title, passage citation, Torah reference)


def links_of(spec: MidrashSpec, links: Sequence[Link]) -> list[Link]:
    """The links whose passage is in ``spec``'s midrash."""
    return [
        link
        for link in links
        if link[0] == spec.toc_title or link[0].startswith(spec.toc_title + ", ")
    ]


def build(spec: MidrashSpec, tanakh: dict[str, Any], links: Sequence[Link]) -> list[dict[str, Any]]:
    """The midrash lined up with each book of the Torah that it is linked to."""
    text, license_name = chosen_text(spec)
    verse_counts = {
        book["en"]: [len(chapter) for chapter in book["chapters"]]
        for book in tanakh["books"]
        if book["en"] in TORAH_BOOKS
    }
    found: dict[tuple[str, int, int], dict[tuple[str, int, int], str]] = defaultdict(dict)
    for title, citation, torah in links_of(spec, links):
        node = title[len(spec.toc_title) + 2 :]
        tail = CITATION_TAIL.match(citation[len(title) :])
        if tail is None:
            continue
        chapter = int(tail["chapter"])
        segment = int(tail["segment"]) if tail["segment"] else None
        passage = passage_at(text, node, chapter, segment)
        if passage is None:
            continue
        html = f"<b>{label(spec, node, chapter, segment)}</b> {shorten(passage)}"
        for verse in verses_of(torah, verse_counts):
            found[verse][(node, chapter, segment or 0)] = html

    books = []
    for book in tanakh["books"]:
        if book["en"] not in TORAH_BOOKS:
            continue
        chapters = [
            [
                "<br><br>".join(
                    found[(book["en"], number, verse)][key]
                    for key in sorted(found[(book["en"], number, verse)])[:MAX_PASSAGES_PER_VERSE]
                )
                for verse in range(1, len(chapter) + 1)
            ]
            for number, chapter in enumerate(book["chapters"], start=1)
        ]
        covered = sum(1 for chapter in chapters for block in chapter if block)
        print(f"  {book['en']:<12} {covered:>5} verses", file=sys.stderr)
        if covered:
            books.append(
                {"en": book["en"], "he": book["he"], "license": license_name, "chapters": chapters}
            )
    return books


def write_archive(target: Path, archive_id: str, books: Sequence[dict[str, Any]]) -> None:
    """Write ``header.json`` and a member per book, in canonical book order."""
    header = {
        "id": archive_id,
        "books": [{"en": b["en"], "he": b["he"], "license": b["license"]} for b in books],
    }
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(
            "header.json", json.dumps(header, ensure_ascii=False, separators=(",", ":"))
        )
        for book in books:
            member = json.dumps(book, ensure_ascii=False, separators=(",", ":"))
            archive.writestr(f"{book['en']}.json", member)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a midrash's archive under data/.")
    parser.add_argument("--midrash", choices=sorted(SPECS), action="append")
    chosen = parser.parse_args(argv).midrash or sorted(SPECS)
    specs = [SPECS[name] for name in chosen]
    with gzip.open(TANAKH_PATH, "rt", encoding="utf-8") as handle:
        tanakh = json.load(handle)
    print("Reading the links…", file=sys.stderr)
    wanted = [link for link in torah_links() if any(links_of(spec, [link]) for spec in specs)]
    for spec in specs:
        print(f"Building {spec.id}…", file=sys.stderr)
        books = build(spec, tanakh, wanted)
        if not books:
            raise SystemExit(f"{spec.id}: no verse of the Torah is linked to it")
        target = DATA_DIR / f"{spec.id}.zip"
        write_archive(target, spec.id, books)
        print(f"Wrote {target}: {target.stat().st_size / 1024 / 1024:.2f} MB", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
