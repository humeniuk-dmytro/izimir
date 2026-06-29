"""Tests for the scheduled scan: it must always report to the owner.

A working schedule that finds nothing must still send a summary, otherwise it
looks broken to the owner (the original "cron doesn't work" complaint).
"""

from __future__ import annotations

from izimir import scheduler as S
from izimir import texts
from izimir.config import Settings


def make_settings():
    return Settings(
        api_id=1,
        api_hash="x",
        bot_token="x",
        owner_id=777,
        db_path=":memory:",
        user_session="u",
        bot_session="b",
    )


class FakeBot:
    def __init__(self):
        self.msgs = []

    async def send_message(self, owner, text, **k):
        self.msgs.append((owner, text))


async def test_scheduled_scan_reports_even_when_nothing_found(db, monkeypatch):
    async def fake_scan(uc, bc, d, s, hours_override=None):
        return (2, 10, 0, 0)

    monkeypatch.setattr(S, "run_scan", fake_scan)
    bot = FakeBot()
    await S.run_scheduled_scan(None, bot, db, make_settings())

    assert bot.msgs, "owner must be notified even with 0 found"
    owner, text = bot.msgs[0]
    assert owner == 777
    assert texts.SCHEDULED_PREFIX in text
    assert "Найдено: 0" in text
    assert texts.SCAN_NOTHING_NEW in text  # checked>0, found==0


async def test_scheduled_scan_reports_found(db, monkeypatch):
    async def fake_scan(uc, bc, d, s, hours_override=None):
        return (2, 50, 3, 0)

    monkeypatch.setattr(S, "run_scan", fake_scan)
    bot = FakeBot()
    await S.run_scheduled_scan(None, bot, db, make_settings())

    text = bot.msgs[0][1]
    assert texts.SCHEDULED_PREFIX in text
    assert "Найдено: 3" in text
    assert texts.SCAN_NOTHING_NEW not in text


async def test_scheduled_scan_notifies_owner_on_failure(db, monkeypatch):
    async def boom(uc, bc, d, s, hours_override=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(S, "run_scan", boom)
    bot = FakeBot()
    await S.run_scheduled_scan(None, bot, db, make_settings())

    assert bot.msgs[0][1] == texts.SCAN_FAILED
