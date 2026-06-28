"""Case/diacritic-insensitive text normalization shared by search and storage.

Used both for keyword matching in the scanner and for case-insensitive
keyword de-duplication in the DB layer (SQLite's COLLATE NOCASE only folds
ASCII, so it cannot dedupe Cyrillic/Turkish keywords by case).
"""

from __future__ import annotations

import unicodedata

import snowballstemmer

# Turkish dotted/dotless I variants all map to plain "i" so that keyword
# "satılık" matches text "SATILIK" (whose .lower() is "satilik") and
# "İzmir"/"IZMIR"/"izmir" all match each other.
_I_MAP = str.maketrans({"İ": "i", "I": "i", "ı": "i", "i": "i"})

_RU_STEMMER = snowballstemmer.stemmer("russian")


def fold(text: str) -> str:
    """Normalize for case/diacritic-insensitive comparison (RU/UA/TR)."""
    text = text.translate(_I_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def _is_cyrillic(text: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in text)


def stem_key(keyword: str) -> str:
    """Reduce a keyword to a search stem so it matches inflected forms.

    The stem is searched as a substring of folded message text, so it must be
    a prefix of every inflected form:

    * Cyrillic (ru/uk): Russian Snowball stem on the folded word — e.g.
      ``квартира`` → ``квартир``, which then matches «квартиру», «квартиры»,
      «в квартире». Endings in Slavic languages mutate the word tail, which is
      why a plain substring of the full form fails and stemming is needed.
    * Latin (tr): keep the folded base. Turkish is agglutinative — suffixes are
      appended — so the base ``kiralık`` is already a substring of «kiralıktır».

    Empty/odd stems fall back to the folded keyword so matching never breaks.
    """
    folded = fold(keyword)
    if _is_cyrillic(keyword):
        return _RU_STEMMER.stemWord(folded) or folded
    return folded
