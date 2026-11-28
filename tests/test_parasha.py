"""Tests for app/parasha.py and /api/parasha: the weekly portion cut into seven days."""

from datetime import date
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient

from app.corpus import load_corpus
from app.main import app
from app.parasha import (
    ParashaError,
    load_portions,
    split_by_words,
    week_plan,
    week_start,
)


@pytest.fixture(scope="session")
def corpus():
    return load_corpus()


class TestLoadPortions:
    def test_holds_the_fifty_four_portions_running_on_without_a_gap(self, corpus):
        portions = load_portions()
        assert len(portions) == 54
        book_index = {book["he"]: i for i, book in enumerate(corpus.books)}
        order = [(v.book_index, v.chapter, v.number) for v in corpus.verses if v.book_index < 5]
        position = {key: i for i, key in enumerate(order)}
        for before, after in pairwise(portions):
            first_after = position[(book_index[after.book], *after.start)]
            last_before = position[(book_index[before.book], *before.end)]
            assert first_after == last_before + 1
        assert portions[0].start == (1, 1)
        assert portions[-1].end == (34, 12)


class TestWeekStart:
    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (date(2026, 11, 21), date(2026, 11, 21)),  # Saturday starts its own week
            (date(2026, 11, 22), date(2026, 11, 21)),  # Sunday
            (date(2026, 11, 27), date(2026, 11, 21)),  # Friday closes it
            (date(2026, 11, 28), date(2026, 11, 28)),  # the next Saturday starts the next
        ],
    )
    def test_is_the_saturday_on_or_before(self, day, expected):
        assert week_start(day) == expected


class TestSplitByWords:
    @pytest.mark.parametrize(
        ("counts", "parts", "expected"),
        [
            ([5] * 7, 7, [(i, i) for i in range(7)]),  # one verse each
            ([1] * 14, 7, [(i * 2, i * 2 + 1) for i in range(7)]),  # even runs
            (
                [10, 1, 1, 1, 1, 1, 1, 1],
                7,
                [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 7)],
            ),
        ],
    )
    def test_cuts_at_the_verse_boundary_nearest_each_even_share(self, counts, parts, expected):
        assert split_by_words(counts, parts) == expected

    def test_covers_every_verse_once_and_in_order(self):
        counts = [3, 9, 2, 7, 7, 1, 12, 4, 4, 6, 8, 2, 5, 5, 9, 1, 3, 10]
        runs = split_by_words(counts)
        assert runs[0][0] == 0 and runs[-1][1] == len(counts) - 1
        assert all(after[0] == before[1] + 1 for before, after in pairwise(runs))

    def test_rejects_fewer_verses_than_parts(self):
        with pytest.raises(ValueError, match="cannot make"):
            split_by_words([4, 4, 4], 7)


class TestWeekPlan:
    def test_studies_the_portion_read_on_the_closing_shabbat(self, corpus):
        plan = week_plan(corpus, date(2026, 11, 26), israel=True)  # a Thursday
        assert plan.week_start == date(2026, 11, 21)
        assert plan.read_on == date(2026, 11, 28)
        assert [portion.he for portion in plan.portions] == ["וישלח"]

    def test_makes_seven_days_from_saturday_to_friday_covering_the_portion(self, corpus):
        plan = week_plan(corpus, date(2026, 11, 26), israel=True)
        assert [day.day for day in plan.days] == [1, 2, 3, 4, 5, 6, 7]
        assert plan.days[0].date == date(2026, 11, 21)  # ראשון on Shabbat
        assert plan.days[6].date == date(2026, 11, 27)  # שביעי on Friday
        assert plan.days[0].start == plan.portions[0].start
        assert plan.days[6].end == plan.portions[0].end

    def test_keeps_the_days_close_in_length(self, corpus):
        words = [day.words for day in week_plan(corpus, date(2026, 11, 26), israel=True).days]
        assert max(words) - min(words) < 0.15 * sum(words) / 7

    def test_skips_a_holiday_shabbat_to_the_next_portion(self, corpus):
        # The Shabbat of Chol HaMoed Sukkot 5787 reads no portion.
        plan = week_plan(corpus, date(2026, 9, 28), israel=True)
        assert plan.read_on > date(2026, 10, 3)
        assert plan.portions

    def test_a_combined_week_reads_both_portions(self, corpus):
        plan = week_plan(corpus, date(2027, 7, 24), israel=True)  # Matot-Masei
        assert [portion.he for portion in plan.portions] == ["מטות", "מסעי"]
        assert plan.days[0].start == plan.portions[0].start
        assert plan.days[6].end == plan.portions[1].end

    def test_raises_when_no_portion_is_found(self, corpus, monkeypatch):
        monkeypatch.setattr("app.parasha.portions_read_on", lambda shabbat, israel: ())
        with pytest.raises(ParashaError) as error:
            week_plan(corpus, date(2026, 11, 26), israel=True)
        assert error.value.code == "no_portion"


class TestParashaEndpoint:
    def test_json_shape(self):
        body = TestClient(app).get("/api/parasha", params={"day": "2026-11-26"}).json()
        assert body.keys() == {"weekStart", "readOn", "portions", "days"}
        assert body["days"][0].keys() == {"day", "date", "book", "start", "end", "words", "hebrew"}
        assert body["days"][0]["start"].keys() == {"chapter", "verse", "chapterHe", "verseHe"}

    def test_gives_each_day_its_hebrew_date(self):
        days = TestClient(app).get("/api/parasha", params={"day": "2026-11-28"}).json()["days"]
        assert days[0]["date"] == "2026-11-28"  # a Saturday starts its own week
        assert days[0]["hebrew"] == {
            "day": 18,
            "dayHe": "י״ח",
            "monthHe": "כסלו",
            "monthEn": "Kislev",
            "year": 5787,
            "yearHe": "תשפ״ז",
        }
        assert [day["hebrew"]["day"] for day in days] == list(range(18, 25))  # a day apiece

    @pytest.mark.parametrize("day", ["", "not-a-date", "2026-13-40"])
    def test_rejects_a_bad_date(self, day):
        assert TestClient(app).get("/api/parasha", params={"day": day}).status_code == 422

    def test_israel_and_diaspora_can_differ(self):
        client = TestClient(app)
        # After Pesach the two schedules are a week apart until they meet at Balak.
        week = {"day": "2027-06-12"}
        israel = client.get("/api/parasha", params={**week, "israel": "true"}).json()
        diaspora = client.get("/api/parasha", params={**week, "israel": "false"}).json()
        assert [p["en"] for p in israel["portions"]] == ["Beha'alotcha"]
        assert [p["en"] for p in diaspora["portions"]] == ["Nasso"]
