"""Тести логіки пошуку: нормалізація fold(), стемінг і матчинг.

Доводимо, що:
  * пошук регістронезалежний для RU/UA/TR;
  * турецькі İ/I/ı/i не ламають збіг (реальний баг B-TR);
  * стемінг ловить словоформи: «квартира» знаходить «квартиру/квартиры»;
  * кейс друга: Cartier × {квартира, снять} не збігається.
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
    """Як у run_scan: ключі проганяються через stem_key."""
    return [stem_key(k) for k in keywords]


# --- базова нормалізація -------------------------------------------------


@pytest.mark.parametrize(
    "keyword, text",
    [
        ("снять", "СНЯТЬ квартиру в центре"),
        ("Снять", "хочу снять жильё"),
        ("квартира", "Сдаётся КВАРТИРА посуточно"),
        ("оренда", "Довгострокова ОРЕНДА житла"),  # українська
        ("продам", "ПРОДАМ срочно"),
    ],
)
def test_case_insensitive_cyrillic(keyword, text):
    assert text_matches(text, _keys(keyword))


def test_no_false_match():
    assert not text_matches("продаю велосипед", _keys("квартира", "снять"))


def test_empty_text_never_matches():
    assert not text_matches("", _keys("квартира"))


# --- стемінг / словоформи (нове) -----------------------------------------


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
    # один ключ «квартира» ловить усі відмінки
    assert text_matches(text, _keys("квартира"))


def test_rent_keyword_inflections():
    assert text_matches("сдам в аренду", _keys("аренда"))
    assert text_matches("долгосрочная аренда жилья", _keys("аренда"))


def test_distinct_roots_do_not_collide():
    # «продажа» не повинна ловити «велосипед» тощо
    assert not text_matches("куплю велосипед", _keys("продажа"))


# --- турецький регістр (реальний баг B-TR) -------------------------------


@pytest.mark.parametrize(
    "keyword, text",
    [
        ("satılık", "ACİL SATILIK daire"),  # ı проти .lower()-i
        ("satılık", "satılık ev sahibinden"),
        ("kiralık", "KİRALIK daire İzmir"),
        ("kiralık", "kiralıktır, eşyalı"),  # турецький суфікс -tır
        ("İzmir", "izmir merkezde kiralık"),
        ("izmir", "IZMIR bornova satılık"),
        ("ev", "Satılık EV deniz manzaralı"),
    ],
)
def test_turkish_case_insensitive(keyword, text):
    assert text_matches(text, _keys(keyword)), f"{keyword!r} має збігтись у {text!r}"


def test_turkish_i_variants_fold_equal():
    assert fold("İzmir") == fold("IZMIR") == fold("izmir") == fold("İZMİR")


def test_plain_lower_would_have_failed():
    # Доказ, що звичайний .lower() НЕ впорався б — саме тому потрібен fold().
    assert "satılık" not in "ACİL SATILIK daire".lower()
    assert text_matches("ACİL SATILIK daire", _keys("satılık"))


# --- відтворення кейсу друга --------------------------------------------


def test_friend_case_cartier_vs_rent_keywords_no_match():
    # Друг шукав «квартира»/«снять» — браслет Cartier не містить цих слів.
    assert not text_matches(CARTIER, _keys("квартира", "снять"))


def test_friend_case_cartier_vs_relevant_keywords_match():
    # За словами, що реально є в тексті, оголошення знаходиться.
    assert text_matches(CARTIER, _keys("продам", "грамм"))
