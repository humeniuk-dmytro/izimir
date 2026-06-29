"""Tests for run_scan: time window, dedup, metrics, matching.

Telegram clients are mocked, the DB is a real in-memory one. This reproduces
the full scan path without the network.
"""

from __future__ import annotations

import datetime as dt

from telethon.tl.types import User

from izimir.config import Settings
from izimir.scanner import run_scan


def make_settings(scan_hours=24, messages_limit=500):
    return Settings(
        api_id=1,
        api_hash="x",
        bot_token="x",
        owner_id=111,
        db_path=":memory:",
        user_session="u",
        bot_session="b",
        scan_hours=scan_hours,
        messages_limit=messages_limit,
        rate_limit_delay=0.0,
    )


class FakeMessage:
    def __init__(self, id, text, minutes_ago=1):
        self.id = id
        self.text = text
        self.date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
        self.sender = User(id=900 + id, first_name="Author", username=f"author{id}")


class FakeUserClient:
    """Returns the given messages from iter_messages (newest-first order)."""

    def __init__(self, messages):
        self._messages = messages
        self.resolved = []

    async def get_entity(self, arg):
        self.resolved.append(arg)
        return object()  # not a Channel → group_username stays None

    def iter_messages(self, entity, limit=None):
        messages = self._messages

        async def gen():
            for m in messages:
                yield m

        return gen()


class FakeBotClient:
    def __init__(self):
        self.sent = []

    async def send_message(self, owner_id, body, buttons=None, parse_mode=None):
        self.sent.append((owner_id, body, buttons))


async def _seed_group_and_keywords(db, keywords):
    await db.add_group(123, "https://t.me/baraholka", "Барахолка", 555)
    for kw in keywords:
        await db.add_keyword(kw)


async def test_finds_fresh_matching_message(db):
    await _seed_group_and_keywords(db, ["квартира"])
    user = FakeUserClient([FakeMessage(1, "Сдаётся квартира в центре")])
    bot = FakeBotClient()

    groups, checked, found, errors = await run_scan(user, bot, db, make_settings())

    assert groups == 1
    assert checked == 1
    assert found == 1
    assert errors == 0
    assert len(bot.sent) == 1
    assert bot.sent[0][0] == 111  # owner_id
    assert await db.is_processed(1, 123)


async def test_old_messages_break_scan(db):
    await _seed_group_and_keywords(db, ["квартира"])
    # newest-first: fresh (matches), then old (outside the window → break)
    user = FakeUserClient(
        [
            FakeMessage(2, "квартира свежая", minutes_ago=10),
            FakeMessage(1, "квартира старая", minutes_ago=60 * 30),  # 30 hours ago
        ]
    )
    bot = FakeBotClient()

    groups, checked, found, errors = await run_scan(
        user, bot, db, make_settings(scan_hours=24)
    )

    assert checked == 1  # the old one wasn't even checked (break before the counter)
    assert found == 1


async def test_scan_hours_window_respected(db):
    await _seed_group_and_keywords(db, ["квартира"])
    # message 2 hours ago; window is only 1 hour → out of range
    user = FakeUserClient([FakeMessage(1, "квартира", minutes_ago=120)])
    bot = FakeBotClient()

    groups, checked, found, errors = await run_scan(
        user, bot, db, make_settings(scan_hours=1)
    )

    assert checked == 0
    assert found == 0
    assert bot.sent == []


async def test_dedup_skips_already_processed(db):
    await _seed_group_and_keywords(db, ["квартира"])
    await db.mark_processed(1, 123)  # already sent earlier
    user = FakeUserClient([FakeMessage(1, "квартира снова")])
    bot = FakeBotClient()

    groups, checked, found, errors = await run_scan(user, bot, db, make_settings())

    assert checked == 1
    assert found == 0  # the duplicate is not re-sent
    assert bot.sent == []


async def test_metrics_count_all_checked(db):
    await _seed_group_and_keywords(db, ["квартира"])
    user = FakeUserClient(
        [
            FakeMessage(1, "продаю велосипед"),  # no match
            FakeMessage(2, "сдаётся квартира"),  # match
            FakeMessage(3, "куплю авто"),  # no match
        ]
    )
    bot = FakeBotClient()

    groups, checked, found, errors = await run_scan(user, bot, db, make_settings())

    assert checked == 3
    assert found == 1


async def test_no_keywords_returns_zero(db):
    await db.add_group(123, "https://t.me/baraholka", "Барахолка", 555)
    user = FakeUserClient([FakeMessage(1, "квартира")])
    bot = FakeBotClient()

    result = await run_scan(user, bot, db, make_settings())

    assert result == (0, 0, 0, 0)
    assert bot.sent == []


async def test_turkish_keyword_matches_in_scan(db):
    await _seed_group_and_keywords(db, ["satılık"])
    user = FakeUserClient([FakeMessage(1, "ACİL SATILIK daire İzmir")])
    bot = FakeBotClient()

    groups, checked, found, errors = await run_scan(user, bot, db, make_settings())

    assert found == 1  # Turkish case no longer breaks the search


async def test_keyword_matches_inflected_form_in_scan(db):
    # the nominative key "квартира" should find the accusative "квартиру" (stemming)
    await _seed_group_and_keywords(db, ["квартира"])
    user = FakeUserClient([FakeMessage(1, "Сниму квартиру на длительный срок")])
    bot = FakeBotClient()

    groups, checked, found, errors = await run_scan(user, bot, db, make_settings())

    assert found == 1


async def test_lead_persisted_on_match(db):
    await _seed_group_and_keywords(db, ["квартира"])
    user = FakeUserClient([FakeMessage(1, "сдается квартира в центре")])
    bot = FakeBotClient()

    await run_scan(user, bot, db, make_settings())

    finds = await db.recent_finds()
    assert len(finds) == 1
    assert finds[0]["message_id"] == 1
    assert "квартира" in finds[0]["text"]


async def test_hours_override_widens_window(db):
    await _seed_group_and_keywords(db, ["квартира"])
    # message 100 hours ago — outside the standard 24-hour window
    narrow = await run_scan(
        FakeUserClient([FakeMessage(1, "квартира", minutes_ago=100 * 60)]),
        FakeBotClient(),
        db,
        make_settings(scan_hours=24),
    )
    assert narrow[2] == 0  # found

    deep = await run_scan(
        FakeUserClient([FakeMessage(1, "квартира", minutes_ago=100 * 60)]),
        FakeBotClient(),
        db,
        make_settings(scan_hours=24),
        hours_override=200,
    )
    assert deep[2] == 1  # the deep scan finds it
