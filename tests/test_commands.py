"""Tests for the command menu and /scan N parsing."""

from __future__ import annotations

import re

import pytest

from izimir import texts
from izimir.bot_handlers import register_handlers, set_bot_commands
from izimir.config import Settings

# The same pattern as in cmd_scan — we pin the expected parsing behavior.
SCAN_RE = re.compile(r"^/scan(?:\s+(\d+))?$")


def make_settings():
    return Settings(
        api_id=1,
        api_hash="x",
        bot_token="x",
        owner_id=111,
        db_path=":memory:",
        user_session="u",
        bot_session="b",
    )


class CaptureBot:
    """Captures registered handlers and outgoing messages/files."""

    def __init__(self):
        self.handlers = {}
        self.sent = []
        self.files = []

    def on(self, event):
        def deco(func):
            self.handlers[func.__name__] = func
            return func

        return deco

    async def send_message(self, *a, **k):
        self.sent.append((a, k))

    async def send_file(self, *a, **k):
        self.files.append((a, k))


class FakeEvent:
    def __init__(self, sender_id, raw_text):
        self.sender_id = sender_id
        self.raw_text = raw_text
        self.responses = []

    async def respond(self, text, **k):
        self.responses.append(text)


class FakeBot:
    def __init__(self):
        self.request = None

    async def __call__(self, request):
        self.request = request
        return None


async def test_set_bot_commands_sends_valid_menu():
    bot = FakeBot()
    await set_bot_commands(bot)
    assert bot.request is not None
    cmds = bot.request.commands
    assert len(cmds) == len(texts.BOT_COMMANDS)
    for c in cmds:
        # Telegram limits: command lowercase, ≤32; description ≤256
        assert c.command == c.command.lower()
        assert 1 <= len(c.command) <= 32
        assert 1 <= len(c.description) <= 256


@pytest.mark.parametrize(
    "text, group",
    [
        ("/scan", None),
        ("/scan 72", "72"),
        ("/scan   5", "5"),
    ],
)
def test_scan_pattern_matches(text, group):
    m = SCAN_RE.match(text)
    assert m is not None
    assert m.group(1) == group


@pytest.mark.parametrize("text", ["/scan abc", "/scanx", "/scan 5 5", "/scan-1"])
def test_scan_pattern_rejects(text):
    assert SCAN_RE.match(text) is None


# --- integration: /stats, /export, /reset_seen actually run --------------


async def test_stats_export_reset_run(db):
    await db.add_find(1, 1, "Недвижимость", "Аня", "anya", "сдается квартира", "lnk")
    settings = make_settings()
    bot = CaptureBot()
    register_handlers(bot, user_client=None, db=db, settings=settings)
    h = bot.handlers

    ev = FakeEvent(settings.owner_id, "/stats")
    await h["cmd_stats"](ev)
    assert ev.responses and "Всего" in ev.responses[0]

    ev = FakeEvent(settings.owner_id, "/export")
    await h["cmd_export"](ev)
    assert bot.files, "export should have sent a CSV file"

    await db.mark_processed(1, 1)
    ev = FakeEvent(settings.owner_id, "/reset_seen")
    await h["cmd_reset_seen"](ev)
    assert ev.responses
    assert not await db.is_processed(1, 1)


async def test_stats_empty(db):
    settings = make_settings()
    bot = CaptureBot()
    register_handlers(bot, user_client=None, db=db, settings=settings)
    ev = FakeEvent(settings.owner_id, "/stats")
    await bot.handlers["cmd_stats"](ev)
    assert ev.responses == [texts.STATS_EMPTY]
