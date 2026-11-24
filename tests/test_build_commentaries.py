"""Tests for scripts/build_commentaries.py, on synthetic data (no network)."""

import json
import zipfile

import pytest

from scripts import build_commentaries as build
from scripts.build_dataset import BOOKS

BOOK_NAMES = [name for _, name in BOOKS]
BIG = {"license": "Public Domain", "text": [["א", "ב", "ג", "ד"]]}


class TestBaseBook:
    @pytest.mark.parametrize(
        ("title", "prefix", "expected"),
        [
            ("Ibn Ezra on Genesis", "Ibn Ezra on ", "Genesis"),
            ("Onkelos Genesis", "Onkelos ", "Genesis"),
            ("Ibn Ezra HaKatzar on Exodus", "Ibn Ezra on ", None),  # a sibling, not this one
            ("Second Version of Ibn Ezra on Esther", "Ibn Ezra on ", None),
            ("Ibn Ezra on Nowhere", "Ibn Ezra on ", None),
        ],
    )
    def test_names_the_book_only_for_the_commentarys_own_title(self, title, prefix, expected):
        assert build.base_book(title, prefix, BOOK_NAMES) == expected


class TestAlign:
    @pytest.mark.parametrize(
        ("text", "counts", "expected"),
        [
            # Short chapters and short books are padded to the verses the book has.
            ([["א"]], [3, 2], [["א", "", ""], ["", ""]]),
            # Several comments on a verse run together; a comment keeps its <b>.
            ([[["א", "<b>ב</b>"]]], [1], [["א <b>ב</b>"]]),
            # More commentary than verses: the chapter is skipped, not misaligned.
            ([["א", "ב", "ג"], ["ד"]], [2, 1], [["", ""], ["ד"]]),
            # A tag outside the allowed few is stripped; an allowed one loses its attributes.
            ([["<i>א</i>"]], [1], [["א"]]),
            ([['<b onmouseover="x()">א</b><br/>']], [1], [["<b>א</b><br>"]]),
        ],
    )
    def test_lines_the_commentary_up_with_the_books_verses(self, text, counts, expected):
        assert build.align(text, counts, "Test") == expected


class TestUsableText:
    @pytest.mark.parametrize(
        ("text", "verses"),
        [
            ([["א", "ב"], [["ג"]]], 3),
            ([["", "ב"]], 1),
            ({"Introduction": ["א"]}, 0),  # keyed by section
            (["א", "ב"], 0),  # a bare string where a chapter's verses belong
            ([[{"x": 1}]], 0),
        ],
    )
    def test_counts_commented_verses_or_rejects_a_shape_it_cannot_line_up(self, text, verses):
        assert build.usable_text(text) == verses


class TestChooseVersion:
    @staticmethod
    def export(monkeypatch, versions):
        def fetch(url):
            if url.endswith("merged.json"):
                return {"versions": [[name, "src"] for name in versions]}
            name = url.rsplit("/", 1)[1].removesuffix(".json").replace("%20", " ")
            return versions[name]

        monkeypatch.setattr(build, "fetch_json", fetch)

    @pytest.mark.parametrize(
        ("versions", "chosen"),
        [
            ({"a": BIG}, "a"),
            ({"a": dict(BIG, license="unknown"), "b": BIG}, "b"),  # a license not allowed
            ({"a": {"license": "Public Domain", "text": [["א"]]}, "b": BIG}, "b"),  # too thin
            (
                {"a": BIG, "b": {"license": "Public Domain", "text": [["א", "ב", "ג", "ד", "ה"]]}},
                "b",  # the fuller of two
            ),
            ({"a": dict(BIG, license="CC-BY-SA")}, None),  # nothing allowed
        ],
    )
    def test_takes_the_fullest_allowed_version(self, monkeypatch, versions, chosen):
        self.export(monkeypatch, versions)
        found = build.choose_version("https://x/", build.SPECS["ibn-ezra"])
        assert found == (versions[chosen] if chosen else None)


class TestWriteArchive:
    def test_writes_a_header_and_a_member_per_book(self, tmp_path):
        books = [{"en": "Genesis", "he": "בראשית", "license": "CC-BY-NC", "chapters": [["א"]]}]
        target = tmp_path / "x.zip"
        build.write_archive(target, build.SPECS["onkelos"], books)
        with zipfile.ZipFile(target) as archive:
            header = json.loads(archive.read("header.json"))
            member = json.loads(archive.read("Genesis.json"))
        assert header == {
            "id": "onkelos",
            "books": [{"en": "Genesis", "he": "בראשית", "license": "CC-BY-NC"}],
        }
        assert member["chapters"] == [["א"]]
