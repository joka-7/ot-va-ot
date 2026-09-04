"""Hebrew text normalization primitives.

Everything in this module is a pure function over strings, with no dependency on
the corpus or the web framework. Getting these right is the whole ballgame: the
Tanakh text carries niqqud (vowel points) and ta'amei hamikra (cantillation),
words are joined by maqaf rather than spaces, verses end in sof pasuq, and five
Hebrew letters take a different shape at the end of a word. None of that should
affect whether a name matches a verse.
"""

from __future__ import annotations

import re

# Niqqud, ta'amei hamikra, and the Hebrew marks that sit between them.
#
#   U+0591-U+05AF  ta'amei hamikra (cantillation)
#   U+05B0-U+05BD  niqqud (vowel points) through meteg
#   U+05BF         rafe
#   U+05C0         paseq
#   U+05C1-U+05C2  shin dot / sin dot
#   U+05C3         sof pasuq  (the ׃ that ends every verse)
#   U+05C4-U+05C5  marks above/below
#   U+05C7         qamats qatan
#
# U+05BE (maqaf, ־) is deliberately *excluded*: it joins two words, so it is
# treated as a word separator rather than as a mark to be dropped.
MARKS = re.compile(r"[֑-ֽֿ-ׇׅ]")

# The 22 Hebrew consonants, including the five final forms.
HEBREW_LETTERS = r"א-ת"
NON_LETTERS = re.compile(f"[^{HEBREW_LETTERS}]+")

# אותיות מנצפ"ך סופיות — final forms mapped onto their regular counterparts, so
# that a name ending in ם matches a verse ending in מ and vice versa.
FINALS = {
    "ך": "כ",  # ך -> כ
    "ם": "מ",  # ם -> מ
    "ן": "נ",  # ן -> נ
    "ף": "פ",  # ף -> פ
    "ץ": "צ",  # ץ -> צ
}

_FINALS_TABLE = str.maketrans(FINALS)


def strip_marks(text: str) -> str:
    """Remove niqqud, cantillation, and sof pasuq, leaving letters and maqaf."""
    return MARKS.sub("", text)


def letters_only(text: str) -> str:
    """Keep only Hebrew consonants.

    Drops maqaf, sof pasuq, geresh/gershayim, apostrophes, quotation marks,
    whitespace, digits and Latin characters, so that the first and last
    *letters* of a verse can be identified without punctuation getting in the
    way. Final forms are left as-is; call :func:`normalize_finals` for that.
    """
    return NON_LETTERS.sub("", strip_marks(text))


def normalize_finals(text: str) -> str:
    """Rewrite final letter forms as their regular forms (ם -> מ, ן -> נ, …)."""
    return text.translate(_FINALS_TABLE)


def normalize(text: str) -> str:
    """Full normalization: letters only, with final forms folded away.

    This is the canonical form used for every comparison the app makes.
    """
    return normalize_finals(letters_only(text))


def words(text: str) -> list[str]:
    """Split text into normalized words.

    Marks are stripped first, then the text is split on anything that is not a
    Hebrew letter — which means maqaf separates the words it joins, so
    ``עַל־פְּנֵי`` yields ``["על", "פני"]`` rather than one fused token.
    """
    stripped = strip_marks(text)
    return [normalize_finals(word) for word in NON_LETTERS.split(stripped) if word]


def first_last(text: str) -> tuple[str, str]:
    """Return the first and last Hebrew letters of ``text``, finals normalized.

    Raises:
        ValueError: if the text contains no Hebrew letters at all.
    """
    letters = normalize(text)
    if not letters:
        raise ValueError("no Hebrew letters found")
    return letters[0], letters[-1]


def has_hebrew(text: str) -> bool:
    """True if the text contains at least one Hebrew consonant."""
    return bool(letters_only(text))


# --- Hebrew numerals (gematria) ---------------------------------------------

_GEMATRIA = [
    (400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"),
    (90, "צ"), (80, "פ"), (70, "ע"), (60, "ס"), (50, "נ"),
    (40, "מ"), (30, "ל"), (20, "כ"), (10, "י"),
    (9, "ט"), (8, "ח"), (7, "ז"), (6, "ו"), (5, "ה"),
    (4, "ד"), (3, "ג"), (2, "ב"), (1, "א"),
]


def he_number(value: int) -> str:
    """Format an integer as a Hebrew numeral, e.g. 1 -> א׳, 15 -> ט״ו, 231 -> רל״א.

    Follows the usual conventions: 15 and 16 are written ט״ו and ט״ז rather than
    spelling out the divine name, a single letter takes a geresh (׳), and
    multiple letters take a gershayim (״) before the last one.
    """
    if value <= 0:
        return str(value)

    letters: list[str] = []
    remainder = value
    while remainder > 0:
        # 15 and 16 would otherwise be written יה and יו.
        if remainder == 15:
            letters.append("טו")
            break
        if remainder == 16:
            letters.append("טז")
            break
        for number, letter in _GEMATRIA:
            if remainder >= number:
                letters.append(letter)
                remainder -= number
                break

    text = "".join(letters)
    if len(text) == 1:
        return f"{text}׳"  # geresh
    return f"{text[:-1]}״{text[-1]}"  # gershayim before the final letter


# --- Raw-offset mapping (used for highlighting) ------------------------------
#
# The API highlights matched letters inside the *original* verse text, which
# still carries niqqud and cantillation. That means translating positions in the
# normalized form back to offsets in the raw string. Combining marks always
# follow their base letter in Unicode, so a highlight that starts at a letter
# must be extended forward to swallow the marks that belong to it — otherwise a
# letter gets highlighted while its vowel does not.


def is_letter(char: str) -> bool:
    """True if the character is a Hebrew consonant."""
    return "א" <= char <= "ת"


# Paseq (U+05C0) and sof pasuq (U+05C3) match MARKS so that stripping removes
# them, but they are spacing punctuation rather than marks attached to a letter.
# They must not be swallowed into a highlight, and they do end a word.
PUNCTUATION_MARKS = frozenset("\u05C0\u05C3")


def is_mark(char: str) -> bool:
    """True if the character is a combining niqqud/cantillation mark.

    Excludes paseq and sof pasuq, which are punctuation that happens to live in
    the same Unicode range.
    """
    return bool(MARKS.fullmatch(char)) and char not in PUNCTUATION_MARKS


def mark_end(text: str, index: int) -> int:
    """Return the offset just past the letter at ``index`` and its trailing marks."""
    end = index + 1
    while end < len(text) and is_mark(text[end]):
        end += 1
    return end


def letter_positions(text: str) -> list[int]:
    """Raw offsets of every Hebrew consonant in ``text``, in order.

    Position ``i`` in the result is the raw offset of character ``i`` of
    ``normalize(text)``, which is what makes the two representations lineup.
    """
    return [i for i, char in enumerate(text) if is_letter(char)]


class Word:
    """One word of a verse, with enough information to highlight it precisely."""

    __slots__ = ("text", "start", "end", "positions")

    def __init__(self, text: str, start: int, end: int, positions: list[int]):
        self.text = text           # normalized (letters only, finals folded)
        self.start = start         # raw offset of the word's first letter
        self.end = end             # raw offset just past its last letter + marks
        self.positions = positions  # raw offset of each letter in `text`

    def span_of(self, needle: str) -> tuple[int, int] | None:
        """Raw offsets covering ``needle`` inside this word, or None if absent."""
        at = self.text.find(needle)
        if at < 0:
            return None
        return self.positions[at], self.positions[at + len(needle) - 1] + 1


def word_spans(text: str) -> list[Word]:
    """Split ``text`` into :class:`Word` objects that remember their raw offsets.

    Word boundaries are the same as in :func:`words`: anything that is not a
    Hebrew consonant ends the current word, so maqaf splits the words it joins,
    while niqqud and cantillation stay attached to the word around them.
    """
    result: list[Word] = []
    letters: list[str] = []
    positions: list[int] = []
    start = 0

    def flush(end: int) -> None:
        if letters:
            result.append(Word(normalize_finals("".join(letters)), start, end, list(positions)))
            letters.clear()
            positions.clear()

    end = 0
    for index, char in enumerate(text):
        if is_letter(char):
            if not letters:
                start = index
            letters.append(char)
            positions.append(index)
            end = index + 1
        elif is_mark(char):
            if letters:
                end = index + 1  # a mark belongs to the word it trails
        else:
            flush(end)
    flush(end)
    return result
