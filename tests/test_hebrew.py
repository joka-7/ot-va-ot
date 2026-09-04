"""Tests for the Hebrew normalization primitives."""

from app.hebrew import (
    first_last,
    he_number,
    letters_only,
    normalize,
    normalize_finals,
    strip_marks,
    word_spans,
    words,
)

# Genesis 1:2, which exercises niqqud, cantillation, maqaf and sof pasuq.
VERSE = "וְהָאָ֗רֶץ הָיְתָ֥ה תֹ֙הוּ֙ וָבֹ֔הוּ וְחֹ֖שֶׁךְ עַל־פְּנֵ֣י תְה֑וֹם׃"


class TestStripping:
    def test_marks_are_removed(self):
        assert strip_marks("בְּרֵאשִׁ֖ית") == "בראשית"

    def test_sof_pasuq_is_removed(self):
        assert "׃" not in strip_marks(VERSE)

    def test_maqaf_survives_stripping_as_a_separator(self):
        assert "־" in strip_marks(VERSE)

    def test_letters_only_drops_punctuation_and_spaces(self):
        assert letters_only("עַל־פְּנֵ֣י׃") == "עלפני"

    def test_latin_and_digits_are_dropped(self):
        assert letters_only("David 123 דוד") == "דוד"


class TestFinalLetters:
    def test_all_five_finals_fold(self):
        assert normalize_finals("ךםןףץ") == "כמנפצ"

    def test_normalize_combines_stripping_and_folding(self):
        assert normalize("אַבְרָהָם") == "אברהמ"

    def test_final_and_regular_forms_are_equal_after_folding(self):
        assert normalize("שלום") == normalize("שלומ")


class TestWords:
    def test_maqaf_splits_the_words_it_joins(self):
        assert "עלפני" not in words(VERSE)
        assert "על" in words(VERSE)
        assert "פני" in words(VERSE)

    def test_words_are_normalized(self):
        # וְחֹשֶׁךְ ends in a final kaf, which folds to a regular kaf.
        assert "וחשכ" in words(VERSE)

    def test_word_count(self):
        assert len(words(VERSE)) == 8  # maqaf makes על־פני two words


class TestFirstLast:
    def test_verse_first_and_last_letters_ignore_marks(self):
        # Opens with ו (וְהָאָרֶץ), closes with the ם of תְהוֹם -- not the sof pasuq.
        assert first_last(VERSE) == ("ו", "מ")

    def test_name_final_letter_folds(self):
        assert first_last("אברהם") == ("א", "מ")

    def test_single_letter_name(self):
        assert first_last("ב") == ("ב", "ב")

    def test_name_without_hebrew_is_rejected(self):
        import pytest

        with pytest.raises(ValueError):
            first_last("David")


class TestWordSpans:
    def test_spans_point_at_the_raw_text(self):
        spans = word_spans("בְּרֵאשִׁ֖ית בָּרָ֣א")
        assert [w.text for w in spans] == ["בראשית", "ברא"]
        raw = "בְּרֵאשִׁ֖ית בָּרָ֣א"
        assert raw[spans[0].start:spans[0].end] == "בְּרֵאשִׁ֖ית"

    def test_span_of_maps_a_substring_back_to_raw_offsets(self):
        raw = "אֱלֹהִ֑ים"
        word = word_spans(raw)[0]
        start, end = word.span_of("אלהי")
        assert raw[start:end].startswith("אֱ")
        assert "ם" not in raw[start:end]

    def test_sof_pasuq_is_not_pulled_into_a_word(self):
        raw = "תְה֑וֹם׃"
        word = word_spans(raw)[0]
        assert "׃" not in raw[word.start:word.end]


class TestHebrewNumerals:
    def test_units_and_tens(self):
        assert he_number(1) == "א׳"
        assert he_number(9) == "ט׳"
        assert he_number(11) == "י״א"
        assert he_number(20) == "כ׳"

    def test_fifteen_and_sixteen_avoid_the_divine_name(self):
        assert he_number(15) == "ט״ו"
        assert he_number(16) == "ט״ז"

    def test_hundreds(self):
        assert he_number(150) == "ק״נ"
        assert he_number(231) == "רל״א"
        # Psalms runs to 150 chapters; Isaiah 66; nothing needs more than this.
        assert he_number(119) == "קי״ט"
