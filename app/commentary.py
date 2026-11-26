"""Commentaries shown beside a chapter but never searched: Onkelos, Ibn Ezra, Metzudat David.

Rashi sits inside ``data/tanakh.json.gz`` with the verses. These are far more text and
need no index, so each is one zip (``scripts/build_commentaries.py``) with a member per
book, read when a chapter of that book is first asked for. Only the last few books stay
in memory.
"""

from __future__ import annotations

import json
import threading
import zipfile
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CACHE_SIZE = 4


class CommentaryError(LookupError):
    """A commentary request that cannot be served; ``code`` is the stable API error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CommentaryConfigError(RuntimeError):
    """``ENABLED_COMMENTARIES`` names something unknown, or a data file is missing."""


@dataclass(frozen=True)
class Commentary:
    """One display-only commentary: who it is and where its archive is."""

    id: str
    he: str
    en: str
    fr: str
    data_file: str  # under data/
    clamp: bool = False  # long notes, shown shortened with a "show more" control

    @property
    def data_path(self) -> Path:
        """Where the archive is, under ``data/``."""
        return DATA_DIR / self.data_file

    def as_dict(self) -> dict[str, str | bool]:
        """The JSON shape of one entry in ``GET /api/books``'s ``commentaries``."""
        shape: dict[str, str | bool] = {"id": self.id, "he": self.he, "en": self.en, "fr": self.fr}
        return {**shape, "clamp": True} if self.clamp else shape


def _commentary(
    id: str, he: str, en: str, fr: str | None = None, clamp: bool = False
) -> Commentary:
    return Commentary(id, he, en, fr or en, f"{id}.zip", clamp)


# In the order the reader lists them: the translations, then the Rishonim, then the Acharonim,
# then the midrashim (long passages, built by scripts/build_midrashim.py).
KNOWN_COMMENTARIES: tuple[Commentary, ...] = (
    _commentary("onkelos", "תרגום אונקלוס", "Targum Onkelos"),
    _commentary("targum-jonathan", "תרגום יונתן", "Targum Jonathan"),
    _commentary("rashbam", "רשב״ם", "Rashbam"),
    _commentary("ibn-ezra", "אבן עזרא", "Ibn Ezra"),
    _commentary("ralbag", "רלב״ג", "Ralbag"),
    _commentary("sforno", "ספורנו", "Sforno"),
    _commentary("daat-zekenim", "דעת זקנים", "Da'at Zekenim"),
    _commentary("metzudat-david", "מצודת דוד", "Metzudat David"),
    _commentary("or-hachaim", "אור החיים", "Or HaChaim"),
    _commentary("kli-yakar", "כלי יקר", "Kli Yakar"),
    _commentary("malbim", "מלבי״ם", "Malbim"),
    _commentary("mekhilta", "מכילתא דרבי ישמעאל", "Mekhilta d'Rabbi Yishmael", clamp=True),
    _commentary("tanchuma-buber", "תנחומא (בובר)", "Midrash Tanchuma (Buber)", clamp=True),
    _commentary("sifrei-devarim", "ספרי דברים", "Sifrei Devarim", clamp=True),
)


@dataclass(frozen=True)
class StoredBook:
    """One book's commentary: ``chapters[c - 1][v - 1]`` is verse ``v`` of chapter ``c``."""

    license: str | None
    chapters: Sequence[Sequence[str]]


@dataclass(frozen=True)
class ChapterCommentary:
    """A commentary's text on each verse of one chapter."""

    commentary: Commentary
    license: str | None
    verses: list[tuple[int, str]]  # (verse number, text), only verses it has text on

    def as_dict(self) -> dict[str, Any]:
        """The JSON shape of ``GET /api/commentary``."""
        return {
            "commentary": self.commentary.as_dict(),
            "license": self.license,
            "verses": [{"verse": number, "text": text} for number, text in self.verses],
        }


class CommentaryStore:
    """One commentary's archive, read a book at a time."""

    def __init__(
        self,
        info: Commentary,
        path: Path | None = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ):
        """Open an archive and read its header.

        Args:
            info: The commentary this archive holds.
            path: The archive; ``info.data_path`` unless a test supplies another.
            cache_size: How many books to keep in memory.
        """
        self.info = info
        self._path = path or info.data_path
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, StoredBook] = OrderedDict()
        with zipfile.ZipFile(self._path) as archive:
            header = json.loads(archive.read("header.json"))
        self._books = {book["en"] for book in header["books"]}

    def book(self, book_en: str) -> StoredBook | None:
        """The commentary on a book, or ``None`` if it has none.

        Args:
            book_en: The book's English name, e.g. ``"Genesis"``.
        """
        if book_en not in self._books:
            return None
        with self._lock:
            if book_en in self._cache:
                self._cache.move_to_end(book_en)
                return self._cache[book_en]
        # Read outside the lock, so a cached book never waits on this read. Two first
        # requests for one book may each read it; the second keeps the first's copy.
        with zipfile.ZipFile(self._path) as archive:
            member = json.loads(archive.read(f"{book_en}.json"))
        stored = StoredBook(member["license"], member["chapters"])
        with self._lock:
            stored = self._cache.setdefault(book_en, stored)
            self._cache.move_to_end(book_en)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return stored


class CommentaryStores:
    """The enabled display-only commentaries."""

    def __init__(self, enabled: Sequence[Commentary], cache_size: int = DEFAULT_CACHE_SIZE):
        """Open each enabled commentary's archive.

        Raises:
            CommentaryConfigError: If one is listed twice or its data file is missing.
        """
        ids = [info.id for info in enabled]
        if len(set(ids)) != len(ids):
            raise CommentaryConfigError("a commentary is listed more than once")
        for info in enabled:
            if not info.data_path.is_file():
                raise CommentaryConfigError(f"data file for {info.id!r} is missing")
        self._stores = {info.id: CommentaryStore(info, cache_size=cache_size) for info in enabled}

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> CommentaryStores:
        """Build the registry from ``ENABLED_COMMENTARIES`` (comma-separated ids).

        Unset means every known commentary: their data ships in the repository and
        costs little memory, so a host that never sets the variable still serves them.
        Set but empty means none.

        Raises:
            CommentaryConfigError: If a listed id is not a known commentary.
        """
        known = {info.id: info for info in KNOWN_COMMENTARIES}
        if "ENABLED_COMMENTARIES" not in environ:
            return cls(list(KNOWN_COMMENTARIES))
        ids = [part.strip() for part in environ["ENABLED_COMMENTARIES"].split(",")]
        ids = [commentary_id for commentary_id in ids if commentary_id]
        unknown = [commentary_id for commentary_id in ids if commentary_id not in known]
        if unknown:
            raise CommentaryConfigError(
                f"ENABLED_COMMENTARIES names unknown commentaries {unknown}; known: {sorted(known)}"
            )
        return cls([known[commentary_id] for commentary_id in ids])

    def infos(self) -> list[Commentary]:
        """The enabled commentaries, in configured order."""
        return [store.info for store in self._stores.values()]

    def on_chapter(
        self, commentary_id: str, book_en: str, chapter: int, verse_count: int
    ) -> ChapterCommentary:
        """A commentary's text on each verse of one chapter.

        Args:
            commentary_id: The commentary, e.g. ``"ibn-ezra"``.
            book_en: The book's English name.
            chapter: The chapter number, from 1.
            verse_count: How many verses the chapter has; text past it is ignored.

        Returns:
            The verses it has text on, in order. A book or chapter it does not cover
            gives no verses rather than an error.

        Raises:
            CommentaryError: With code ``unknown_commentary`` if it is not enabled.
        """
        store = self._stores.get(commentary_id)
        if store is None:
            raise CommentaryError("unknown_commentary")
        stored = store.book(book_en)
        if stored is None or chapter > len(stored.chapters):
            return ChapterCommentary(store.info, None, [])
        verses = [
            (number, text)
            for number, text in enumerate(stored.chapters[chapter - 1][:verse_count], start=1)
            if text
        ]
        return ChapterCommentary(store.info, stored.license, verses)
