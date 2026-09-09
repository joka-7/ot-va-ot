"""Tests for the Rashi-alignment logic in scripts/build_dataset.py.

These run against synthetic data rather than the network -- the point is the
*alignment* logic (padding short chapters, dropping over-long ones), which is
exactly the part most likely to silently misattribute a comment to the wrong
verse if it regresses.
"""

from scripts.build_dataset import align_rashi, clean_rashi_comment


class TestCleanRashiComment:
    def test_keeps_allowed_tags(self):
        assert clean_rashi_comment("<b>ד״ה.</b> פירוש <small>הערה</small>:") == (
            "<b>ד״ה.</b> פירוש <small>הערה</small>:"
        )

    def test_strips_disallowed_tags(self):
        """Only the tag itself is stripped, like any HTML-tag removal -- its
        text content is kept, same as a comment's other running text."""
        assert clean_rashi_comment('<i>alert</i><b>שלום</b>') == "alert<b>שלום</b>"

    def test_collapses_whitespace(self):
        assert clean_rashi_comment("שלום   \n  עולם") == "שלום עולם"


class TestAlignRashi:
    def test_pads_a_short_chapter(self):
        """Sefaria trims trailing verses with no comment; they come back as
        empty strings rather than being dropped."""
        chapters = [["verse one", "verse two", "verse three"]]
        rashi = [[["comment one"], ["comment two"]]]  # verse three: no comment
        aligned = align_rashi(chapters, rashi, "Test")
        assert aligned == [["comment one", "comment two", ""]]

    def test_joins_multiple_comments_per_verse(self):
        chapters = [["verse one"]]
        rashi = [[["<b>first.</b> a:", "<b>second.</b> b:"]]]
        aligned = align_rashi(chapters, rashi, "Test")
        assert aligned == [["<b>first.</b> a: <b>second.</b> b:"]]

    def test_drops_an_overlong_chapter_rather_than_misattribute(self):
        """A chapter boundary mismatch (real case: Exodus 38) must never let a
        comment land on the wrong verse -- the whole chapter goes without
        Rashi instead."""
        chapters = [["verse one", "verse two"]]
        rashi = [[["a"], ["b"], ["c"]]]  # one more "verse" than the text has
        aligned = align_rashi(chapters, rashi, "Test")
        assert aligned == [["", ""]]

    def test_missing_rashi_entirely_yields_all_blanks(self):
        chapters = [["verse one", "verse two"], ["verse three"]]
        aligned = align_rashi(chapters, None, "Test")
        assert aligned == [["", ""], [""]]

    def test_missing_trailing_chapters_are_padded_too(self):
        """Rashi's own array can be shorter than the book's chapter count
        (e.g. commentary that stops partway through, as in Job)."""
        chapters = [["verse one"], ["verse two"]]
        rashi = [[["a"]]]  # only one chapter's worth
        aligned = align_rashi(chapters, rashi, "Test")
        assert aligned == [["a"], [""]]
