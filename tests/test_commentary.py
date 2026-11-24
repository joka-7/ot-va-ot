"""Tests for app/commentary.py and /api/commentary, on the real archives."""

import pytest
from fastapi.testclient import TestClient

from app.commentary import (
    KNOWN_COMMENTARIES,
    CommentaryConfigError,
    CommentaryError,
    CommentaryStore,
    CommentaryStores,
)
from app.main import app

ONKELOS, IBN_EZRA, METZUDAT_DAVID = KNOWN_COMMENTARIES
GENESIS = "בראשית"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestCommentaryStore:
    def test_reads_a_book_from_the_real_archive_and_keeps_the_last_few(self):
        store = CommentaryStore(ONKELOS, cache_size=1)
        genesis = store.book("Genesis")
        assert genesis is not None
        assert genesis.license == "CC-BY-NC"
        assert store.book("Genesis") is genesis  # served from memory
        store.book("Exodus")
        assert store.book("Genesis") is not genesis  # pushed out by the cache of one

    def test_a_book_it_does_not_cover_is_none(self):
        assert CommentaryStore(ONKELOS).book("Isaiah") is None  # Onkelos is on the Torah


class TestCommentaryStores:
    @pytest.mark.parametrize(
        ("environ", "ids"),
        [
            ({}, []),
            ({"ENABLED_COMMENTARIES": ""}, []),
            ({"ENABLED_COMMENTARIES": " onkelos ,"}, ["onkelos"]),
            ({"ENABLED_COMMENTARIES": "ibn-ezra,onkelos"}, ["ibn-ezra", "onkelos"]),
        ],
    )
    def test_enables_what_the_environment_lists_in_that_order(self, environ, ids):
        stores = CommentaryStores.from_environ(environ)
        assert [info.id for info in stores.infos()] == ids

    @pytest.mark.parametrize(
        "enabled",
        [
            [ONKELOS, ONKELOS],  # listed twice
            [type(ONKELOS)("x", "א", "X", "X", "missing.zip")],  # no data file
        ],
    )
    def test_an_invalid_set_stops_startup(self, enabled):
        with pytest.raises(CommentaryConfigError):
            CommentaryStores(enabled)

    def test_an_unknown_id_stops_startup(self):
        with pytest.raises(CommentaryConfigError, match="unknown commentaries"):
            CommentaryStores.from_environ({"ENABLED_COMMENTARIES": "nope"})

    @pytest.mark.parametrize(
        ("commentary", "book", "chapter", "verses", "first_verse"),
        [
            ("onkelos", "Genesis", 1, 31, 1),
            ("onkelos", "Genesis", 1, 5, 1),  # text past the chapter's verse count is ignored
            ("metzudat-david", "Isaiah", 1, 31, 1),
            ("onkelos", "Isaiah", 1, 31, None),  # a book the commentary does not cover
            ("ibn-ezra", "Genesis", 1, 31, None),  # Sefaria has no allowed version of it
            ("onkelos", "Genesis", 999, 31, None),  # a chapter past the end
        ],
    )
    def test_gives_the_verses_it_has_text_on(self, commentary, book, chapter, verses, first_verse):
        stores = CommentaryStores.from_environ({"ENABLED_COMMENTARIES": commentary})
        found = stores.on_chapter(commentary, book, chapter, verses)
        assert (found.verses[0][0] if found.verses else None) == first_verse
        assert len(found.verses) <= verses

    def test_rejects_a_commentary_that_is_not_enabled(self):
        stores = CommentaryStores.from_environ({"ENABLED_COMMENTARIES": "onkelos"})
        with pytest.raises(CommentaryError) as raised:
            stores.on_chapter("ibn-ezra", "Genesis", 1, 31)
        assert raised.value.code == "unknown_commentary"


class TestCommentaryEndpoint:
    def test_books_lists_the_enabled_commentaries(self, client):
        listed = client.get("/api/books").json()["commentaries"]
        assert [c["id"] for c in listed] == ["onkelos", "ibn-ezra", "metzudat-david"]
        assert listed[0] == ONKELOS.as_dict()

    def test_gives_a_chapters_verses_with_the_licence(self, client):
        params = {"book": GENESIS, "chapter": 1, "commentary": "onkelos"}
        body = client.get("/api/commentary", params=params).json()
        assert body["commentary"]["id"] == "onkelos"
        assert body["license"] == "CC-BY-NC"
        assert [v["verse"] for v in body["verses"]][:2] == [1, 2]
        assert "<script" not in "".join(v["text"] for v in body["verses"])

    @pytest.mark.parametrize(
        ("params", "status", "code"),
        [
            ({"book": GENESIS, "chapter": 1, "commentary": "nope"}, 404, "unknown_commentary"),
            ({"book": "nope", "chapter": 1, "commentary": "onkelos"}, 404, "unknown_book"),
            ({"book": GENESIS, "chapter": 99, "commentary": "onkelos"}, 404, "chapter_not_found"),
            ({"book": GENESIS, "chapter": 0, "commentary": "onkelos"}, 422, None),
        ],
    )
    def test_reports_what_it_cannot_serve(self, client, params, status, code):
        response = client.get("/api/commentary", params=params)
        assert response.status_code == status
        if code:
            assert response.json()["code"] == code
