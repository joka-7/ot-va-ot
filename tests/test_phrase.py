"""Tests for free-text word and phrase search.

Like test_search.py, most of these run against the real committed corpus: the
point is that the actual Tanakh gives the answer we expect.
"""

import pytest
from fastapi.testclient import TestClient

from app.corpus import load_corpus
from app.hebrew import MARKS, normalize, word_spans
from app.main import app
from app.phrase import (
    InvalidPhrase,
    PhraseQuery,
    matched_word_indexes,
    pointed_words,
    search_phrase,
)


@pytest.fixture(scope="session")
def corpus():
    return load_corpus()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def refs(group):
    return [verse["ref"] for verse in group["verses"]]


class TestPhraseQuery:
    @pytest.mark.parametrize(
        ("raw", "code"),
        [
            ("", "empty_text"),
            ("   ", "empty_text"),
            ("abc", "invalid_phrase"),
            ("123 !?", "invalid_phrase"),
            ("א", "too_short"),
            ("א" * 201, "too_long"),
            (" ".join(["אב"] * 13), "too_long"),
        ],
    )
    def test_rejects_unsearchable_text(self, raw, code):
        with pytest.raises(InvalidPhrase) as error:
            PhraseQuery.parse(raw)
        assert error.value.code == code

    def test_folds_final_letters(self):
        query = PhraseQuery.parse("מלך ים")
        assert [word.plain for word in query.words] == ["מלכ", "ימ"]

    def test_comma_is_just_punctuation(self):
        assert len(PhraseQuery.parse("אברהם, יצחק").words) == 2

    def test_niqqud_is_tracked_per_word(self):
        query = PhraseQuery.parse("בְּרֵאשִׁית ברא")
        assert query.words[0].pointed is not None
        assert query.words[1].pointed is None
        assert query.uses_niqqud

    def test_query_without_niqqud_does_not_use_it(self):
        assert not PhraseQuery.parse("בראשית ברא").uses_niqqud

    def test_cantillation_in_the_query_is_ignored(self):
        with_accent = PhraseQuery.parse("בְּרֵאשִׁ֖ית")
        without = PhraseQuery.parse("בְּרֵאשִׁית")
        assert with_accent.words == without.words

    def test_ordered_flag_is_kept(self):
        assert PhraseQuery.parse("אל אל", ordered=False).ordered is False
        assert PhraseQuery.parse("אל אל").ordered is True


class TestPointedWords:
    def test_keeps_niqqud_and_drops_cantillation(self):
        (word,) = pointed_words("בְּרֵאשִׁ֖ית")
        assert word == pointed_words("בְּרֵאשִׁית")[0]
        assert "֖" not in word  # tipcha
        assert "ְ" in word  # sheva

    def test_maqaf_separates_words(self):
        assert len(pointed_words("עַל־פְּנֵי")) == 2

    def test_folds_final_letters(self):
        (word,) = pointed_words("מֶלֶךְ")
        assert "ך" not in word
        assert word.count("כ") == 1

    def test_stays_aligned_with_the_plain_words_across_the_whole_corpus(self, corpus):
        """Highlighting indexes the three word lists together, so they must agree."""

        def counts(verse):
            pointed = len(pointed_words(verse.text))
            return {pointed, len(verse.word_list), len(word_spans(verse.text))}

        assert [v.ref for v in corpus.verses if len(counts(v)) != 1] == []

    def test_every_mark_stays_inside_its_word(self):
        """A mark the plain splitter strips must not split a word here either."""
        every_mark = [chr(c) for c in range(0x0590, 0x0600) if MARKS.match(chr(c))]
        assert every_mark
        assert [m for m in every_mark if len(pointed_words(f"א{m}ב")) != 1] == []


class TestMatchedWordIndexes:
    # Normalized the way Verse.word_list is: final letters folded (אלהים -> אלהימ).
    PLAIN = ("אמר", "אלהימ", "יהי", "אור", "ויהי", "אור")

    def run(self, raw, ordered=True, partial=False, pointed=None):
        query = PhraseQuery.parse(raw, ordered=ordered)
        return matched_word_indexes(query, self.PLAIN, pointed or self.PLAIN, partial)

    @pytest.mark.parametrize(
        ("raw", "ordered", "partial", "expected"),
        [
            ("אלהים יהי", True, False, [1, 2]),  # adjacent, in order
            ("יהי אלהים", True, False, []),  # adjacent but reversed
            ("אמר יהי", True, False, []),  # both present, not adjacent
            ("יהי אלהים", False, False, [1, 2]),  # order does not matter here
            ("אמר אור", False, False, [0, 3, 5]),  # every occurrence of every word
            ("אמר חשך", False, False, []),  # one word missing -> no match
            ("הי", True, False, []),  # not a whole word
            ("הי", True, True, [1, 2, 4]),  # but it is inside longer words
        ],
    )
    def test_matching(self, raw, ordered, partial, expected):
        assert self.run(raw, ordered=ordered, partial=partial) == expected

    def test_repeated_phrase_reports_every_occurrence(self):
        plain = ("אב", "גד", "אב", "גד")
        query = PhraseQuery.parse("אב גד")
        assert matched_word_indexes(query, plain, plain, partial=False) == [0, 1, 2, 3]

    def test_pointed_query_word_must_match_the_vowels(self):
        plain = ("כל", "כל")
        pointed = pointed_words("כֹּל כָּל")
        query = PhraseQuery.parse("כֹּל")
        assert matched_word_indexes(query, plain, pointed, partial=False) == [0]

    def test_unpointed_query_word_matches_any_vowels(self):
        plain = ("כל", "כל")
        pointed = pointed_words("כֹּל כָּל")
        query = PhraseQuery.parse("כל")
        assert matched_word_indexes(query, plain, pointed, partial=False) == [0, 1]


class TestSearchPhrase:
    def test_genesis_opening_is_found_exactly_once(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("בראשית ברא"))
        assert refs(result["exact"]) == ["בראשית א׳:א׳"]

    def test_maqaf_phrase_is_found_by_its_words(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("על פני"))
        assert "בראשית א׳:ב׳" in refs(result["exact"])

    def test_phrase_longer_than_two_words(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("בראשית ברא אלהים את השמים ואת הארץ"))
        assert refs(result["exact"]) == ["בראשית א׳:א׳"]

    def test_phrase_does_not_cross_a_verse_boundary(self, corpus):
        """The last word of Genesis 1:1 and the first of 1:2 are never one phrase."""
        result = search_phrase(corpus, PhraseQuery.parse("הארץ והארץ"))
        assert result["exact"]["total"] == 0

    def test_anywhere_finds_words_in_any_order(self, corpus):
        ordered = search_phrase(corpus, PhraseQuery.parse("אלהים ארץ שמים"))
        anywhere = search_phrase(corpus, PhraseQuery.parse("אלהים ארץ שמים", ordered=False))
        assert ordered["exact"]["total"] == 0
        assert "תהילים ס״ח:ט׳" in refs(anywhere["exact"])

    def test_anywhere_is_a_superset_of_ordered(self, corpus):
        ordered = search_phrase(corpus, PhraseQuery.parse("על פני"), limit=500)
        anywhere = search_phrase(corpus, PhraseQuery.parse("על פני", ordered=False), limit=500)
        assert set(refs(ordered["exact"])) <= set(refs(anywhere["exact"]))
        assert anywhere["exact"]["total"] > ordered["exact"]["total"]

    def test_tiers_never_overlap(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("ארץ"), limit=500)
        assert not set(refs(result["exact"])) & set(refs(result["partial"]))

    def test_partial_tier_finds_words_with_attached_prefixes(self, corpus):
        """Genesis 1:1 has הארץ, never a bare ארץ."""
        result = search_phrase(corpus, PhraseQuery.parse("ארץ"), limit=500)
        assert "בראשית א׳:א׳" in refs(result["partial"])
        assert "בראשית א׳:א׳" not in refs(result["exact"])

    def test_niqqud_narrows_the_results(self, corpus):
        plain = search_phrase(corpus, PhraseQuery.parse("אכל"), limit=500)
        pointed = search_phrase(corpus, PhraseQuery.parse("אָכַל"), limit=500)
        assert 0 < pointed["exact"]["total"] < plain["exact"]["total"]
        assert set(refs(pointed["exact"])) <= set(refs(plain["exact"]))

    def test_cantillation_in_the_query_changes_nothing(self, corpus):
        with_accent = search_phrase(corpus, PhraseQuery.parse("בְּרֵאשִׁ֖ית"), limit=500)
        without = search_phrase(corpus, PhraseQuery.parse("בְּרֵאשִׁית"), limit=500)
        assert refs(with_accent["exact"]) == refs(without["exact"])

    def test_no_match_returns_empty_groups(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("זזזזזזזז"))
        assert result["exact"] == {"total": 0, "verses": []}
        assert result["partial"] == {"total": 0, "verses": []}

    def test_limit_caps_verses_but_reports_the_true_total(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("על פני"), limit=5)
        assert len(result["exact"]["verses"]) == 5
        assert result["exact"]["total"] > 5

    def test_query_summary_is_echoed(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("בראשית ברא"))
        assert result["query"] == {
            "text": "בראשית ברא",
            "words": 2,
            "ordered": True,
            "niqqud": False,
        }


class TestHighlights:
    def test_exact_match_highlights_each_matched_word(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("בראשית ברא"))
        verse = result["exact"]["verses"][0]
        marked = [normalize(verse["text"][h["start"] : h["end"]]) for h in verse["highlights"]]
        assert marked == ["בראשית", "ברא"]
        assert {h["kind"] for h in verse["highlights"]} == {"match"}

    def test_partial_match_highlights_only_the_part_that_matched(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("ארץ"), limit=500)
        verse = next(v for v in result["partial"]["verses"] if v["ref"] == "בראשית א׳:א׳")
        marked = [normalize(verse["text"][h["start"] : h["end"]]) for h in verse["highlights"]]
        assert marked == ["ארצ"]  # inside הארץ, with the final letter folded

    def test_pointed_partial_match_highlights_the_whole_word(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("אָרֶץ"), limit=500)
        for verse in result["partial"]["verses"]:
            for h in verse["highlights"]:
                assert "ארצ" in normalize(verse["text"][h["start"] : h["end"]])

    def test_highlights_are_sorted_and_within_bounds(self, corpus):
        result = search_phrase(corpus, PhraseQuery.parse("על פני"), limit=200)
        for verse in result["exact"]["verses"]:
            starts = [h["start"] for h in verse["highlights"]]
            assert starts == sorted(starts)
            size = len(verse["text"])
            assert all(0 <= h["start"] < h["end"] <= size for h in verse["highlights"])


class TestApi:
    def test_phrase_search(self, client):
        response = client.get("/api/phrase", params={"q": "בראשית ברא"})
        assert response.status_code == 200
        assert response.json()["exact"]["verses"][0]["ref"] == "בראשית א׳:א׳"

    def test_ordered_flag_is_honoured(self, client):
        ordered = client.get("/api/phrase", params={"q": "אלהים ארץ שמים"}).json()
        anywhere = client.get(
            "/api/phrase", params={"q": "אלהים ארץ שמים", "ordered": "false"}
        ).json()
        assert ordered["exact"]["total"] == 0
        assert anywhere["exact"]["total"] > 0

    def test_comma_in_the_text_is_not_a_name_separator(self, client):
        response = client.get("/api/phrase", params={"q": "ויאמר, אלהים"})
        assert response.status_code == 200
        assert response.json()["query"]["words"] == 2

    @pytest.mark.parametrize(
        ("q", "code"),
        [("   ", "empty_text"), ("hello", "invalid_phrase"), ("א", "too_short")],
    )
    def test_errors_carry_a_stable_code(self, client, q, code):
        response = client.get("/api/phrase", params={"q": q})
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == code
        assert body["error"]

    def test_missing_query_is_rejected(self, client):
        assert client.get("/api/phrase").status_code == 422

    def test_limit_is_validated(self, client):
        assert client.get("/api/phrase", params={"q": "על פני", "limit": 0}).status_code == 422
