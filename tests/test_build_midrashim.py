"""Tests for scripts/build_midrashim.py, on synthetic data (no network)."""

import json
import zipfile

import pytest

from scripts import build_midrashim as build

COUNTS = {"Genesis": [3, 2], "Exodus": [4]}


class TestVersesOf:
    @pytest.mark.parametrize(
        ("ref", "expected"),
        [
            ("Genesis 1:2", [("Genesis", 1, 2)]),
            ("Genesis 1:2-3", [("Genesis", 1, 2), ("Genesis", 1, 3)]),
            ("Genesis 1:3-2:1", [("Genesis", 1, 3), ("Genesis", 2, 1)]),  # on across a chapter
            ("Genesis 1:2-9", [("Genesis", 1, 2), ("Genesis", 1, 3)]),  # stops at the chapter's end
            (
                "Genesis 1:1-2:2",
                [("Genesis", c, v) for c, v in ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2))],
            ),
            ("Genesis 3:1", []),  # no such chapter
            ("Exodus 1:5", []),  # no such verse, and it ends the book
            ("Leviticus 1:1", []),  # a book not given
            ("not a ref", []),
        ],
    )
    def test_lists_the_verses_a_reference_covers(self, ref, expected):
        assert build.verses_of(ref, COUNTS) == expected

    def test_skips_a_range_longer_than_the_limit(self):
        counts = {"Genesis": [build.MAX_LINKED_VERSES + 2]}
        assert build.verses_of(f"Genesis 1:1-{build.MAX_LINKED_VERSES + 1}", counts) == []
        assert len(build.verses_of(f"Genesis 1:1-{build.MAX_LINKED_VERSES}", counts)) == (
            build.MAX_LINKED_VERSES
        )


class TestShorten:
    @pytest.mark.parametrize(
        ("text", "limit", "expected"),
        [
            ("short", 10, "short"),
            ("one two three four", 10, "one two…"),  # cut at a word, not inside one
            ("one, two, three", 10, "one, two…"),  # no stray punctuation before the ellipsis
            ("one, two, three", 9, "one…"),  # a word that does not fit is dropped whole
        ],
    )
    def test_cuts_at_a_word_boundary(self, text, limit, expected):
        assert build.shorten(text, limit) == expected


SECTIONED = {"Balak": [["a1", "a2"], [["b1", "b1x"], "b2"]]}
PLAIN = [["c1"], ["d1", "d2"]]


class TestPassageAt:
    @pytest.mark.parametrize(
        ("text", "node", "chapter", "segment", "expected"),
        [
            (SECTIONED, "Balak", 1, 2, "a2"),
            (SECTIONED, "Balak", 2, 1, "b1 b1x"),  # a nested segment is flattened
            (SECTIONED, "Balak", 1, None, "a1 a2"),  # no segment: the whole chapter
            (PLAIN, "", 2, 2, "d2"),
            (SECTIONED, "Pinchas", 1, 1, None),  # no such section
            (PLAIN, "", 3, 1, None),  # no such chapter
            (PLAIN, "", 0, 1, None),
            (PLAIN, "", 1, 5, None),  # no such segment
        ],
    )
    def test_finds_one_passage(self, text, node, chapter, segment, expected):
        assert build.passage_at(text, node, chapter, segment) == expected


class TestLabel:
    @pytest.mark.parametrize(
        ("node", "chapter", "segment", "expected"),
        [
            ("Pischa", 2, 1, "מכילתא פסחא ב׳:א׳"),
            ("", 15, None, "מכילתא ט״ו"),
            ("Unmapped", 1, 1, "מכילתא Unmapped א׳:א׳"),  # an unknown section keeps its key
        ],
    )
    def test_heads_a_passage_in_hebrew(self, node, chapter, segment, expected):
        spec = build.MidrashSpec("x", "X", "מכילתא", frozenset(), {"Pischa": "פסחא"})
        assert build.label(spec, node, chapter, segment) == expected


class TestLinksOf:
    def test_keeps_the_midrash_and_its_sections_but_not_a_sibling(self):
        spec = build.SPECS["mekhilta"]
        mine = ("Mekhilta DeRabbi Yishmael, Tractate Pischa", "c", "Exodus 12:1")
        sibling = ("Mekhilta DeRabbi Shimon Ben Yochai", "c", "Exodus 12:1")
        assert build.links_of(spec, [mine, sibling]) == [mine]


class TestBuild:
    def test_lines_passages_up_with_verses_and_caps_them(self, monkeypatch):
        spec = build.MidrashSpec("x", "Sifrei Devarim", "ספרי", frozenset({"CC0"}))
        monkeypatch.setattr(build, "chosen_text", lambda _: ([["p1", "p2"], ["q1"]], "CC0"))
        tanakh = {
            "books": [
                {"en": "Deuteronomy", "he": "דברים", "chapters": [["v1", "v2"], ["v3"]]},
                {"en": "Isaiah", "he": "ישעיהו", "chapters": [["v"]]},
            ]
        }
        links = [
            ("Sifrei Devarim", "Sifrei Devarim 1:2", "Deuteronomy 1:1"),
            ("Sifrei Devarim", "Sifrei Devarim 2:1", "Deuteronomy 1:1-2"),
            ("Sifrei Devarim", "Sifrei Devarim 9:1", "Deuteronomy 1:2"),  # no such passage
            ("Sifrei Devarim", "garbled", "Deuteronomy 2:1"),
        ]
        (book,) = build.build(spec, tanakh, links)
        assert book["en"] == "Deuteronomy" and book["license"] == "CC0"
        assert book["chapters"][0][0] == "<b>ספרי א׳:ב׳</b> p2<br><br><b>ספרי ב׳:א׳</b> q1"
        assert book["chapters"][0][1] == "<b>ספרי ב׳:א׳</b> q1"
        assert book["chapters"][1] == [""]  # nothing is linked to chapter 2


class TestWriteArchive:
    def test_writes_a_header_and_a_member_per_book(self, tmp_path):
        books = [{"en": "Genesis", "he": "בראשית", "license": "CC0", "chapters": [["א"]]}]
        target = tmp_path / "x.zip"
        build.write_archive(target, "sifrei-devarim", books)
        with zipfile.ZipFile(target) as archive:
            header = json.loads(archive.read("header.json"))
            member = json.loads(archive.read("Genesis.json"))
        assert header == {
            "id": "sifrei-devarim",
            "books": [{"en": "Genesis", "he": "בראשית", "license": "CC0"}],
        }
        assert member["chapters"] == [["א"]]


class TestSpecs:
    def test_tanchuma_names_its_sections_in_hebrew_from_the_parashot(self):
        names = build.SPECS["tanchuma-buber"].node_names or {}
        assert names["Balak"] == "בלק"
        assert names["Appendix to Korach"] == "נספח קרח"
