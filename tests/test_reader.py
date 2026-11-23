"""Tests for app/reader.py: reading one chapter of the Tanakh, on the real data."""

import pytest

from app.corpus import load_corpus
from app.hebrew import normalize
from app.reader import ChapterRef, ReaderError, chapter_page, list_books


@pytest.fixture(scope="session")
def corpus():
    return load_corpus()


class TestChapterPage:
    def test_gives_the_chapters_verses_in_reading_order(self, corpus):
        page = chapter_page(corpus, "בראשית", 1)
        assert [verse.number for verse in page.verses] == list(range(1, 32))
        assert normalize(page.verses[0].text).startswith("בראשית")

    @pytest.mark.parametrize(
        ("book", "chapter", "previous", "next"),
        [
            ("בראשית", 1, None, ChapterRef("בראשית", 2)),  # the first chapter has nothing before it
            ("בראשית", 2, ChapterRef("בראשית", 1), ChapterRef("בראשית", 3)),
            ("בראשית", 50, ChapterRef("בראשית", 49), ChapterRef("שמות", 1)),  # on across a book
            ("שמות", 1, ChapterRef("בראשית", 50), ChapterRef("שמות", 2)),
            ("דברי הימים ב", 36, ChapterRef("דברי הימים ב", 35), None),  # the last chapter
        ],
    )
    def test_neighbours_run_on_across_books_and_stop_at_the_ends(
        self, corpus, book, chapter, previous, next
    ):
        page = chapter_page(corpus, book, chapter)
        assert (page.previous, page.next) == (previous, next)

    @pytest.mark.parametrize(
        ("book", "chapter", "code"),
        [
            ("not a book", 1, "unknown_book"),
            ("", 1, "unknown_book"),
            ("בראשית", 0, "chapter_not_found"),
            ("בראשית", 51, "chapter_not_found"),  # Genesis has 50
            ("עובדיה", 2, "chapter_not_found"),  # Obadiah has one chapter
        ],
    )
    def test_rejects_what_it_cannot_serve_with_a_code(self, corpus, book, chapter, code):
        with pytest.raises(ReaderError) as error:
            chapter_page(corpus, book, chapter)
        assert error.value.code == code

    def test_json_shape(self, corpus):
        body = chapter_page(corpus, "בראשית", 1).as_dict()
        assert body.keys() == {
            "book",
            "section",
            "chapter",
            "chapterHe",
            "ref",
            "verses",
            "previous",
            "next",
        }
        assert body["book"] == {"he": "בראשית", "en": "Genesis", "fr": "Genèse"}
        assert (body["chapter"], body["chapterHe"], body["ref"]) == (1, "א׳", "בראשית א׳")
        assert body["verses"][0].keys() == {"verse", "verseHe", "text", "rashi"}
        assert (body["verses"][0]["verse"], body["verses"][0]["verseHe"]) == (1, "א׳")
        assert body["previous"] is None
        assert body["next"] == {"book": "בראשית", "chapter": 2}

    def test_carries_rashi_where_he_wrote_on_a_verse_and_nothing_where_he_did_not(self, corpus):
        verses = chapter_page(corpus, "בראשית", 1).as_dict()["verses"]
        assert verses[0]["rashi"].startswith("<b>בראשית.</b>")
        assert verses[2]["rashi"] == ""  # Genesis 1:3


class TestListBooks:
    def test_lists_every_book_with_chapters_and_hebrew_numerals_under_a_unique_name(self, corpus):
        books = list_books(corpus)
        assert len(books) == 39
        names = [book["he"] for book in books]
        assert len(set(names)) == len(names)  # the API looks a book up by this name
        genesis = books[0]
        assert (genesis["he"], genesis["en"], genesis["chapters"]) == ("בראשית", "Genesis", 50)
        assert len(genesis["chaptersHe"]) == 50
        assert genesis["chaptersHe"][:3] == ["א׳", "ב׳", "ג׳"]
        assert genesis["chaptersHe"][14] == "ט״ו"  # 15 is not spelled with the divine name
