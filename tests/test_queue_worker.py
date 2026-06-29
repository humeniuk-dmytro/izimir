"""Tests for the Mini App command queue worker (_execute).

Each command type must run its action AND echo an outcome to the owner's chat,
so a Mini App action looks like running the matching bot command by hand.
"""

from __future__ import annotations

from izimir import queue_worker as Q
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
        self.files = []

    async def send_message(self, owner, text, **k):
        self.msgs.append((owner, text))

    async def send_file(self, owner, file, caption=None, **k):
        self.files.append((owner, caption))


async def _run(cmd, db, bot, monkeypatch=None):
    return await Q._execute(cmd, None, bot, db, make_settings())


async def test_notify_sends_text_to_owner(db):
    bot = FakeBot()
    status, result = await _run(
        {"type": "notify", "payload": {"text": "привет"}}, db, bot
    )
    assert status == "done"
    assert bot.msgs == [(777, "привет")]


async def test_export_sends_csv_file(db):
    await db.add_find(1, 1, "Группа", "Автор", None, "квартира", "l")
    bot = FakeBot()
    status, result = await _run({"type": "export", "payload": {}}, db, bot)
    assert status == "done"
    assert bot.files and bot.files[0][0] == 777
    assert "1" in result


async def test_export_empty_notifies(db):
    bot = FakeBot()
    status, result = await _run({"type": "export", "payload": {}}, db, bot)
    assert result == "пусто"
    assert bot.msgs and bot.msgs[0][1] == texts.EXPORT_EMPTY


async def test_remove_group_notifies(db, monkeypatch):
    async def fake_remove(uc, d, link):
        return True

    monkeypatch.setattr(Q, "remove_group_by_link", fake_remove)
    bot = FakeBot()
    status, _ = await _run({"type": "remove_group", "payload": {"link": "x"}}, db, bot)
    assert status == "done"
    assert bot.msgs[0][1] == texts.GROUP_REMOVED


async def test_add_group_notifies_with_title(db, monkeypatch):
    async def fake_add(uc, d, link):
        return "added", "МояГруппа"

    monkeypatch.setattr(Q, "add_group_by_link", fake_add)
    bot = FakeBot()
    status, _ = await _run({"type": "add_group", "payload": {"link": "x"}}, db, bot)
    assert status == "done"
    assert "МояГруппа" in bot.msgs[0][1]


async def test_scan_sends_summary_to_owner(db, monkeypatch):
    async def fake_scan(uc, bc, d, s, hours_override=None):
        return (1, 5, 2, 0)

    monkeypatch.setattr(Q, "run_scan", fake_scan)
    bot = FakeBot()
    status, result = await _run({"type": "scan", "payload": {}}, db, bot)
    assert status == "done"
    assert "найдено: 2" in result
    assert bot.msgs and texts.MINIAPP_ACTION in bot.msgs[0][1]


async def test_unknown_command(db):
    bot = FakeBot()
    status, result = await _run({"type": "bogus", "payload": {}}, db, bot)
    assert status == "error"


def test_scan_summary_appends_nothing_new_on_zero():
    msg = Q._scan_summary(None, 1, 5, 0, 0)
    assert texts.SCAN_NOTHING_NEW in msg
    assert texts.MINIAPP_ACTION in msg
