"""Tests for the search logic: fold() normalization, stemming and matching.

We prove that:
  * search is case-insensitive for RU/UA/TR;
  * Turkish İ/I/ı/i do not break a match (the real B-TR bug);
  * stemming catches word forms: "квартира" finds "квартиру/квартиры";
  * the friend's case: Cartier × {квартира, снять} does not match.
"""

from __future__ import annotations

import pytest

from izimir.normalize import fold, stem_key
from izimir.scanner import text_matches

CARTIER = (
    "Оригинальный браслет Cartier модели Love, 31 грамм золота, пожизненная "
    "гарантия на чистку и полировку изделия в официальных магазинах, "
    "покупался в Стамбуле, чеки имеются, продам за 350000 лир."
)


def _keys(*keywords: str) -> list[str]:
    """As in run_scan: keys are passed through stem_key."""
    return [stem_key(k) for k in keywords]


# --- basic normalization -------------------------------------------------


@pytest.mark.parametrize(
    "keyword, text",
    [
        ("снять", "СНЯТЬ квартиру в центре"),
        ("Снять", "хочу снять жильё"),
        ("квартира", "Сдаётся КВАРТИРА посуточно"),
        ("оренда", "Довгострокова ОРЕНДА житла"),  # Ukrainian
        ("продам", "ПРОДАМ срочно"),
    ],
)
def test_case_insensitive_cyrillic(keyword, text):
    assert text_matches(text, _keys(keyword))


def test_no_false_match():
    assert not text_matches("продаю велосипед", _keys("квартира", "снять"))


def test_empty_text_never_matches():
    assert not text_matches("", _keys("квартира"))


# --- stemming / word forms -----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "сдаётся квартира",
        "сниму квартиру на долгий срок",
        "продам две квартиры",
        "в квартире есть мебель",
        "ищу 2-комнатную квартиру",
    ],
)
def test_keyword_matches_all_inflections(text):
    # a single key "квартира" catches every case form
    assert text_matches(text, _keys("квартира"))


def test_rent_keyword_inflections():
    assert text_matches("сдам в аренду", _keys("аренда"))
    assert text_matches("долгосрочная аренда жилья", _keys("аренда"))


def test_distinct_roots_do_not_collide():
    # "продажа" must not catch "велосипед" and the like
    assert not text_matches("куплю велосипед", _keys("продажа"))


# --- Turkish case (the real B-TR bug) ------------------------------------


@pytest.mark.parametrize(
    "keyword, text",
    [
        ("satılık", "ACİL SATILIK daire"),  # dotless ı vs .lower()-i
        ("satılık", "satılık ev sahibinden"),
        ("kiralık", "KİRALIK daire İzmir"),
        ("kiralık", "kiralıktır, eşyalı"),  # Turkish suffix -tır
        ("İzmir", "izmir merkezde kiralık"),
        ("izmir", "IZMIR bornova satılık"),
        ("ev", "Satılık EV deniz manzaralı"),
    ],
)
def test_turkish_case_insensitive(keyword, text):
    assert text_matches(text, _keys(keyword)), f"{keyword!r} should match in {text!r}"


def test_turkish_i_variants_fold_equal():
    assert fold("İzmir") == fold("IZMIR") == fold("izmir") == fold("İZMİR")


def test_plain_lower_would_have_failed():
    # Proof that a plain .lower() would NOT cope — which is exactly why fold() is needed.
    assert "satılık" not in "ACİL SATILIK daire".lower()
    assert text_matches("ACİL SATILIK daire", _keys("satılık"))


# --- reproduction of the friend's case -----------------------------------


def test_friend_case_cartier_vs_rent_keywords_no_match():
    # The friend searched for "квартира"/"снять" — the Cartier bracelet has neither word.
    assert not text_matches(CARTIER, _keys("квартира", "снять"))


def test_friend_case_cartier_vs_relevant_keywords_match():
    # With words that really are in the text, the listing is found.
    assert text_matches(CARTIER, _keys("продам", "грамм"))
