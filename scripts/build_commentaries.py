#!/usr/bin/env python3
"""Build the commentaries the reader shows beside a chapter but never searches.

Each one is written as ``data/<id>.zip``: a ``header.json`` and one member per
book, read when a chapter of that book is first asked for (``app/commentary.py``).
Rashi is different -- it sits inside ``data/tanakh.json.gz`` -- and is not built
here.

For each book the first version Sefaria lists whose license is allowed is used,
so a book whose only versions are unlicensed or restricted is left out and
reported, not guessed at. The text is lined up with the Tanakh dataset by
position, as Rashi's is: a chapter with more comments than verses is skipped.

    python -m scripts.build_commentaries --commentary onkelos   # or ibn-ezra, metzudat-david

Source : https://github.com/Sefaria/Sefaria-Export
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.build_dataset import BOOKS, clean_rashi_comment

EXPORT = "https://storage.googleapis.com/sefaria-export"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TANAKH_PATH = DATA_DIR / "tanakh.json.gz"


@dataclass(frozen=True)
class CommentarySpec:
    """Where a commentary is in the export and which licenses may be shown."""

    id: str
    toc_path: tuple[str, ...]
    title_prefix: str  # before a book's English name in the commentary's own title
    allowed_licenses: frozenset[str]


SPECS: dict[str, CommentarySpec] = {
    spec.id: spec
    for spec in (
        # Metsudah's Onkelos is CC-BY-NC, the only version Sefaria has of it.
        CommentarySpec(
            "onkelos",
            ("Tanakh", "Targum", "Onkelos"),
            "Onkelos ",
            frozenset({"CC-BY-NC", "Public Domain"}),
        ),
        CommentarySpec(
            "ibn-ezra",
            ("Tanakh", "Rishonim on Tanakh", "Ibn Ezra"),
            "Ibn Ezra on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "metzudat-david",
            ("Tanakh", "Acharonim on Tanakh", "Metzudat David"),
            "Metzudat David on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "targum-jonathan",
            ("Tanakh", "Targum", "Targum Jonathan"),
            "Targum Jonathan on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "ralbag",
            ("Tanakh", "Rishonim on Tanakh", "Ralbag"),
            "Ralbag on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "sforno",
            ("Tanakh", "Rishonim on Tanakh", "Sforno"),
            "Sforno on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "rashbam",
            ("Tanakh", "Rishonim on Tanakh", "Rashbam"),
            "Rashbam on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "or-hachaim",
            ("Tanakh", "Acharonim on Tanakh", "Or HaChaim"),
            "Or HaChaim on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "kli-yakar",
            ("Tanakh", "Acharonim on Tanakh", "Kli Yakar"),
            "Kli Yakar on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "malbim",
            ("Tanakh", "Acharonim on Tanakh", "Malbim"),
            "Malbim on ",
            frozenset({"Public Domain", "CC0"}),
        ),
        CommentarySpec(
            "daat-zekenim",
            ("Tanakh", "Rishonim on Tanakh", "Da'at Zekenim"),
            "Da'at Zekenim on ",
            frozenset({"Public Domain", "CC0"}),
        ),
    )
}


def fetch_json(url: str) -> Any:
    """Read one JSON file from the export; raises ``urllib.error.HTTPError`` if missing."""
    if not url.startswith("https://"):
        raise ValueError(f"refusing to fetch a non-https URL: {url}")
    with urllib.request.urlopen(url, timeout=180) as response:  # nosec B310 - scheme checked above
        return json.loads(response.read().decode("utf-8"))


def toc_leaves(nodes: Sequence[dict[str, Any]], path: Sequence[str]) -> list[dict[str, Any]]:
    """The books under a table-of-contents path, e.g. every ``Ibn Ezra on ...``."""
    for node in nodes:
        if node.get("category") == path[0] or node.get("title") == path[0]:
            children = node.get("contents", [])
            if len(path) == 1:
                return [leaf for child in children for leaf in _leaves(child)]
            return toc_leaves(children, path[1:])
    raise ValueError(f"table of contents has no {'/'.join(path)}")


def _leaves(node: dict[str, Any]) -> list[dict[str, Any]]:
    if "contents" in node:
        return [leaf for child in node["contents"] for leaf in _leaves(child)]
    return [node]


def base_book(title: str, prefix: str, books: Sequence[str]) -> str | None:
    """The Tanakh book a commentary title is on, or ``None`` for any other title.

    Exact, so a sibling such as ``Ibn Ezra HaKatzar on Exodus`` is not mistaken for
    the commentary itself.

    Args:
        title: e.g. ``"Ibn Ezra on Genesis"`` or ``"Onkelos Genesis"``.
        prefix: What comes before the book's name, e.g. ``"Ibn Ezra on "``.
        books: The English book names.
    """
    return next((book for book in books if title == prefix + book), None)


def flatten(verse: object) -> list[str]:
    """One verse's comments as a flat list of non-empty strings."""
    if isinstance(verse, str):
        return [verse] if verse.strip() else []
    if isinstance(verse, list):
        return [comment for part in verse for comment in flatten(part)]
    raise ValueError(f"unexpected {type(verse).__name__} in commentary text")


def align(
    text: list[Any], verse_counts: Sequence[int], book: str
) -> list[list[str]]:
    """Line a commentary's chapters up with the book's, one cleaned block per verse.

    Short chapters are padded (Sefaria trims trailing empty verses). A chapter
    with more verses of commentary than the book has is skipped, as Rashi's is:
    it is split against a different boundary, so position would be wrong.
    """
    aligned: list[list[str]] = []
    for index, count in enumerate(verse_counts):
        chapter = text[index] if index < len(text) else []
        if len(chapter) > count:
            print(
                f"  warning: {book} ch.{index + 1} has {len(chapter)} verses of commentary "
                f"against {count} -- skipping",
                file=sys.stderr,
            )
            aligned.append([""] * count)
            continue
        blocks = [
            " ".join(clean_rashi_comment(comment) for comment in flatten(verse))
            for verse in chapter
        ]
        aligned.append(blocks + [""] * (count - len(blocks)))
    return aligned


# A version commenting on fewer verses than this is not a verse-by-verse commentary but a
# whole chapter's text filed under its first verse (Ibn Ezra on Habakkuk's Daat version).
MIN_COMMENTED_VERSES = 3


def usable_text(text: object) -> int:
    """How many verses a version has comments on, or 0 if it is not chapters of verses.

    A text keyed by section, or with a bare string where a chapter's list of
    verses belongs, cannot be lined up with the verses and is left out.
    """
    if not isinstance(text, list) or not all(isinstance(chapter, list) for chapter in text):
        return 0
    try:
        return sum(1 for chapter in text for verse in chapter if flatten(verse))
    except ValueError:
        return 0


def choose_version(base: str, spec: CommentarySpec) -> dict[str, Any] | None:
    """The allowed version with the most commented verses, or ``None`` if none is usable."""
    merged = fetch_json(base + "merged.json")
    best: tuple[int, dict[str, Any]] | None = None
    for name, *_ in merged["versions"]:
        try:
            version = fetch_json(base + urllib.parse.quote(f"{name}.json"))
        except urllib.error.HTTPError:
            continue
        score = usable_text(version["text"])
        if (
            version.get("license") in spec.allowed_licenses
            and score >= MIN_COMMENTED_VERSES
            and score > (best[0] if best else 0)
        ):
            best = (score, version)
    return best[1] if best else None


def build_book(
    spec: CommentarySpec, leaf: dict[str, Any], tanakh: dict[str, Any]
) -> dict[str, Any] | None:
    """One book's commentary, shaped for the archive, or ``None`` if it cannot be shown."""
    book = base_book(leaf["title"], spec.title_prefix, [name for _, name in BOOKS])
    if book is None:
        print(f"  {leaf['title']}: not on a Tanakh book, left out", file=sys.stderr)
        return None
    path = urllib.parse.quote("/".join([*leaf["categories"], leaf["title"]]))
    chosen = choose_version(f"{EXPORT}/json/{path}/Hebrew/", spec)
    if chosen is None:
        print(f"  {book}: no allowed version, left out", file=sys.stderr)
        return None
    version = chosen
    base = next(entry for entry in tanakh["books"] if entry["en"] == book)
    chapters = align(version["text"], [len(chapter) for chapter in base["chapters"]], book)
    print(
        f"  {book:<16} {sum(1 for c in chapters for v in c if v):>5} verses  "
        f"{version['license']}",
        file=sys.stderr,
    )
    return {"en": book, "he": base["he"], "license": version["license"], "chapters": chapters}


def write_archive(target: Path, spec: CommentarySpec, books: Sequence[dict[str, Any]]) -> None:
    """Write ``header.json`` and a member per book, in canonical book order."""
    header = {
        "id": spec.id,
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
    parser = argparse.ArgumentParser(description="Build a commentary's archive under data/.")
    parser.add_argument("--commentary", choices=sorted(SPECS), required=True)
    spec = SPECS[parser.parse_args(argv).commentary]

    with gzip.open(TANAKH_PATH, "rt", encoding="utf-8") as handle:
        tanakh = json.load(handle)
    toc = fetch_json(f"{EXPORT}/table_of_contents.json")
    leaves = toc_leaves(toc, spec.toc_path)
    print(f"Fetching {spec.id}: {len(leaves)} books…", file=sys.stderr)

    built = {}
    for leaf in leaves:
        result = build_book(spec, leaf, tanakh)
        if result:
            built[result["en"]] = result
    order = [name for _, name in BOOKS]
    books = [built[name] for name in order if name in built]
    if not books:
        raise SystemExit(f"{spec.id}: no book had an allowed version")

    target = DATA_DIR / f"{spec.id}.zip"
    write_archive(target, spec, books)
    print(
        f"\nWrote {target}: {len(books)} books, {target.stat().st_size / 1024 / 1024:.2f} MB",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
