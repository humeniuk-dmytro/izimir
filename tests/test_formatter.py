"""Tests for the notification format and inline buttons (spec §4)."""

from __future__ import annotations

import datetime as dt

from telethon.tl.types import User

from izimir import texts
from izimir.formatter import format_found_message

DATE = dt.datetime(2026, 5, 9, 10, 28, tzinfo=dt.timezone.utc)


class FakeMsg:
    def __init__(self, id, text, sender, date=DATE):
        self.id = id
        self.text = text
        self.sender = sender
        self.date = date


def _button_pairs(buttons):
    """Flatten to list of (text, url). Button.url() yields KeyboardButtonUrl."""
    return [(b.text, b.url) for row in buttons for b in row]


def test_public_group_and_author_with_username():
    sender = User(id=5, first_name="Иван", username="ivan_seller")
    msg = FakeMsg(101, "Сдаётся квартира", sender)
    body, buttons = format_found_message(
        msg, "Барахолка Измир", "baraholka", 123, "https://t.me/baraholka"
    )

    assert texts.FOUND_HEADER in body
    assert "👤 Автор: @ivan_seller" in body
    assert "👥 Группа: Барахолка Измир" in body
    assert "🕒 Дата: 09.05.2026 10:28" in body
    assert "Сдаётся квартира" in body

    pairs = _button_pairs(buttons)
    assert (texts.BTN_OPEN_MESSAGE, "https://t.me/baraholka/101") in pairs
    assert (texts.BTN_OPEN_GROUP, "https://t.me/baraholka") in pairs
    assert (texts.BTN_WRITE_AUTHOR, "https://t.me/ivan_seller") in pairs


def test_private_group_uses_c_link():
    sender = User(id=5, first_name="Иван", username="ivan_seller")
    msg = FakeMsg(77, "kiralık daire", sender)
    body, buttons = format_found_message(
        msg, "Закрытая группа", None, 123456, "https://t.me/+abc"
    )
    pairs = _button_pairs(buttons)
    assert (texts.BTN_OPEN_MESSAGE, "https://t.me/c/123456/77") in pairs
    # for a private group without a username the group button uses the invite link
    assert (texts.BTN_OPEN_GROUP, "https://t.me/+abc") in pairs


def test_author_without_username_uses_tg_id_link():
    sender = User(id=42, first_name="Анна", last_name="П", username=None)
    msg = FakeMsg(1, "продам", sender)
    body, buttons = format_found_message(msg, "G", "g", 1, "l")
    assert "👤 Автор: Анна П" in body
    pairs = _button_pairs(buttons)
    assert (texts.BTN_WRITE_AUTHOR, "tg://user?id=42") in pairs


def test_unknown_author():
    msg = FakeMsg(1, "текст", None)
    body, _ = format_found_message(msg, "G", "g", 1, "l")
    assert f"👤 Автор: {texts.AUTHOR_UNKNOWN}" in body


def test_long_text_truncated():
    sender = User(id=1, first_name="X", username="x")
    long_text = "квартира " * 200  # >1000 символів
    msg = FakeMsg(1, long_text, sender)
    body, _ = format_found_message(msg, "G", "g", 1, "l")
    assert "…" in body
    # the body must not be excessive (truncated to 1000 + wrapper)
    assert len(body) < 1200
