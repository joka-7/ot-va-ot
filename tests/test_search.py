"""Tests for the corpus, the matching logic, and the HTTP API.

These assert against the real committed corpus rather than a fixture: the point
of most of them is that the *actual* Tanakh gives the answer we expect.
"""

import pytest
from fastapi.testclient import TestClient

from app.corpus import load_corpus
from app.hebrew import MARKS, normalize
from app.main import app
from app.search import Name, search


@pytest.fixture(scope="session")
def corpus():
    return load_corpus()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


class TestCorpus:
    def test_verse_and_book_counts(self, corpus):
        assert len(corpus) == 23206
        assert len(corpus.books) == 39  # the 24 books, as Sefaria's 39 files

    def test_canonical_order(self, corpus):
        assert corpus.verses[0].ref == "בראשית א׳:א׳"
        assert corpus.books[0]["he"] == "בראשית"
        assert corpus.books[-1]["he"] == "דברי הימים ב"

    def test_every_verse_has_letters(self, corpus):
        assert all(verse.letters for verse in corpus.verses)

    def test_every_book_has_all_three_names(self, corpus):
        """Every book carries he/en/fr names -- catches a missing translation."""
        for book in corpus.books:
            assert book["he"] and book["en"] and book["fr"]

    def test_known_book_names_in_all_languages(self, corpus):
        genesis = next(b for b in corpus.books if b["he"] == "בראשית")
        assert genesis["en"] == "Genesis"
        assert genesis["fr"] == "Genèse"


class TestCleanedText:
    """The export's editorial apparatus must not leak into the verse text.

    Each of these was a real bug: parasha markers alone gave 3,048 verses the
    wrong final letter, since פ and ס are themselves Hebrew letters.
    """

    def test_no_parasha_markers(self, corpus):
        assert not any("(" in verse.text or ")" in verse.text for verse in corpus.verses)

    def test_no_ketiv_qere_brackets(self, corpus):
        assert not any("[" in verse.text or "]" in verse.text for verse in corpus.verses)

    def test_no_html(self, corpus):
        assert not any("<" in verse.text for verse in corpus.verses)

    def test_no_unpointed_leftovers(self, corpus):
        """Every word is pointed; a bare word would be a stray ketiv."""
        stray = [
            (verse.ref, word)
            for verse in corpus.verses
            for word in verse.text.split()
            if normalize(word) and not MARKS.search(word)
        ]
        assert stray == []

    def test_parasha_marker_no_longer_ends_a_verse(self, corpus):
        """Genesis 1:5 ends "יוֹם אֶחָד׃ (פ)" in the export — its last letter is ד."""
        verse = next(v for v in corpus.verses if v.ref == "בראשית א׳:ה׳")
        assert verse.last == "ד"

    def test_qere_is_kept_over_ketiv(self, corpus):
        """Job 38:1: ketiv מנ הסערה, qere מִן הַסְּעָרָה."""
        verse = next(v for v in corpus.verses if v.ref == "איוב ל״ח:א׳")
        assert "מִ֥ן" in verse.text
        assert "מנ" not in verse.text.split()

    def test_ketiv_velo_qere_is_dropped(self, corpus):
        """Ruth 3:12 writes אם but does not read it."""
        verse = next(v for v in corpus.verses if v.ref == "רות ג׳:י״ב")
        assert "אם" not in verse.text.split()


class TestLetterMatch:
    """The primary custom: verse opens with the name's first letter, closes with its last."""

    @pytest.mark.parametrize(
        "name, expected",
        [("אברהם", 297), ("שרה", 76), ("דוד", 4), ("יונתן", 21)],
    )
    def test_counts(self, corpus, name, expected):
        parsed = Name.parse(name)
        assert len(corpus.letter_matches(parsed.first, parsed.last)) == expected

    def test_matched_verses_really_start_and_end_correctly(self, corpus):
        parsed = Name.parse("אברהם")
        for index in corpus.letter_matches(parsed.first, parsed.last):
            verse = corpus.verses[index]
            assert verse.letters[0] == "א"
            assert verse.letters[-1] == "מ"

    def test_final_letter_names_match_regular_letters(self, corpus):
        """ם and מ are the same letter for this purpose."""
        assert Name.parse("אברהם").last == Name.parse("אברהמ").last


class TestNameInVerse:
    def test_exact_word_is_the_clean_signal(self, corpus):
        # Raw substring matching finds שרה in 918 verses (אשרה, ישרה, the verb
        # שרה); as a standalone word it is 28.
        assert len(corpus.exact_word_matches("שרה")) == 28

    def test_tiers_never_overlap(self, corpus):
        exact = set(corpus.exact_word_matches("שרה"))
        partial = set(corpus.partial_word_matches("שרה"))
        assert exact and partial
        assert not (exact & partial)

    def test_partial_finds_attached_prefixes(self, corpus):
        """ולשרה / השרה live in the partial tier, not the exact one."""
        partial = corpus.partial_word_matches("שרה")
        assert any(
            any("שרה" in word and word != "שרה" for word in corpus.verses[i].word_set)
            for i in partial
        )

    def test_name_is_matched_with_finals_folded(self, corpus):
        assert corpus.exact_word_matches(normalize("אברהם")) == corpus.exact_word_matches("אברהמ")


class TestPairs:
    def test_abraham_and_sarah_have_exactly_one_consecutive_pair(self, corpus):
        result = search(corpus, [Name.parse("אברהם"), Name.parse("שרה")])
        assert len(result["pairs"]["consecutive"]) == 1

    def test_pair_verses_are_adjacent_and_ordered(self, corpus):
        result = search(corpus, [Name.parse("אברהם"), Name.parse("שרה")])
        pair = result["pairs"]["consecutive"][0]
        assert pair["first"]["book"] == pair["second"]["book"]
        assert pair["second"]["verse"] == pair["first"]["verse"] + 1

    def test_pairs_never_cross_a_book_boundary(self, corpus):
        """A book's last verse has no neighbour in the next book."""
        for index, verse in enumerate(corpus.verses[:-1]):
            following = corpus.verses[index + 1]
            if verse.book_index != following.book_index:
                assert corpus.neighbour(verse, 1) is None

    def test_near_miss_leaves_one_verse_between(self, corpus):
        result = search(corpus, [Name.parse("אברהם"), Name.parse("שרה")])
        for pair in result["pairs"]["nearMiss"]:
            assert pair["second"]["verse"] - pair["first"]["verse"] == 2

    def test_single_name_search_has_no_pairs_key(self, corpus):
        assert "pairs" not in search(corpus, [Name.parse("דוד")])


class TestVerseShape:
    def test_book_carries_all_three_languages(self, corpus):
        result = search(corpus, [Name.parse("דוד")])
        verse = result["names"][0]["letterMatch"]["verses"][0]
        assert set(verse["book"]) == {"he", "en", "fr"}
        assert all(verse["book"][lang] for lang in ("he", "en", "fr"))

    def test_gematria_and_plain_numbers_agree(self, corpus):
        from app.hebrew import he_number

        result = search(corpus, [Name.parse("דוד")])
        verse = result["names"][0]["letterMatch"]["verses"][0]
        assert verse["chapterHe"] == he_number(verse["chapter"])
        assert verse["verseHe"] == he_number(verse["verse"])
        assert verse["ref"].endswith(f"{verse['chapterHe']}:{verse['verseHe']}")


class TestHighlights:
    def test_letter_highlights_land_on_the_first_and_last_letters(self, corpus):
        result = search(corpus, [Name.parse("אברהם")])
        for verse in result["names"][0]["letterMatch"]["verses"]:
            kinds = {h["kind"]: h for h in verse["highlights"]}
            text = verse["text"]
            assert normalize(text[kinds["first"]["start"]:kinds["first"]["end"]]) == "א"
            assert normalize(text[kinds["last"]["start"]:kinds["last"]["end"]]) == "מ"

    def test_highlights_are_sorted_and_within_bounds(self, corpus):
        result = search(corpus, [Name.parse("שרה")])
        for group in ("letterMatch", "exactWord", "partialWord"):
            for verse in result["names"][0][group]["verses"]:
                offsets = [(h["start"], h["end"]) for h in verse["highlights"]]
                assert offsets == sorted(offsets)
                assert all(0 <= s < e <= len(verse["text"]) for s, e in offsets)

    def test_name_highlight_covers_the_name(self, corpus):
        result = search(corpus, [Name.parse("אברהם")])
        for verse in result["names"][0]["exactWord"]["verses"]:
            spans = [h for h in verse["highlights"] if h["kind"] == "name"]
            assert spans
            assert all(normalize(verse["text"][h["start"]:h["end"]]) == "אברהמ" for h in spans)


class TestLimits:
    def test_group_reports_the_true_total_while_capping_verses(self, corpus):
        result = search(corpus, [Name.parse("אברהם")], limit=10)
        group = result["names"][0]["letterMatch"]
        assert group["total"] == 297
        assert len(group["verses"]) == 10


class TestApi:
    def test_health(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["verses"] == 23206
        assert body["license"] == "Public Domain"

    def test_single_name(self, client):
        body = client.get("/api/search", params={"names": "דוד"}).json()
        assert body["query"]["mode"] == "single"
        assert body["names"][0]["letterMatch"]["total"] == 4

    def test_two_names(self, client):
        body = client.get("/api/search", params={"names": "אברהם, שרה"}).json()
        assert body["query"]["mode"] == "pair"
        assert len(body["names"]) == 2
        assert len(body["pairs"]["consecutive"]) == 1

    @pytest.mark.parametrize("separator", [",", "،", ";"])
    def test_accepted_separators(self, client, separator):
        body = client.get("/api/search", params={"names": f"אברהם{separator} שרה"}).json()
        assert body["query"]["names"] == ["אברהם", "שרה"]

    def test_non_hebrew_is_rejected(self, client):
        response = client.get("/api/search", params={"names": "David"})
        assert response.status_code == 400
        body = response.json()
        assert "עבריות" in body["error"]
        assert body["code"] == "invalid_name"

    def test_three_names_are_rejected(self, client):
        response = client.get("/api/search", params={"names": "אברהם, שרה, יצחק"})
        assert response.status_code == 400
        body = response.json()
        assert body["error"]
        assert body["code"] == "too_many"

    def test_empty_query_is_rejected(self, client):
        response = client.get("/api/search", params={"names": "  ,  "})
        assert response.status_code == 400
        assert response.json()["code"] == "empty"

    def test_error_code_is_a_stable_contract(self, client):
        """The frontend keys its i18n error text off these exact strings."""
        assert client.get("/api/search", params={"names": "  ,  "}).json()["code"] == "empty"
        assert client.get("/api/search", params={"names": "David"}).json()["code"] == "invalid_name"
        assert client.get("/api/search", params={"names": "א, ב, ג"}).json()["code"] == "too_many"

    def test_random_verse_matches_the_name(self, client):
        body = client.get("/api/random", params={"name": "דוד"}).json()
        letters = normalize(body["verse"]["text"])
        assert letters[0] == "ד" and letters[-1] == "ד"

    def test_random_not_found_carries_a_code(self, client, corpus):
        # גג (first=last=ג) has no letter-match verses in the corpus.
        assert not corpus.letter_matches("ג", "ג")
        response = client.get("/api/random", params={"name": "גג"})
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    def test_spa_is_served_at_the_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert 'dir="rtl"' in response.text
