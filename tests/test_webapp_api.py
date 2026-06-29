"""Tests for the Mini App API endpoints (called directly, no HTTP client).

Env vars are set before importing the app so its module-level ``load_settings``
does not abort on missing config.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from urllib.parse import urlencode

import pytest

os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ.setdefault("OWNER_ID", "777")
os.environ.setdefault("DB_PATH", ":memory:")

from fastapi import HTTPException  # noqa: E402

from izimir.webapp import app as A  # noqa: E402

OWNER = {"id": 777}


class FakeReq:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


def _init_data(uid: int, token: str = "123456:TEST") -> str:
    fields = {
        "auth_date": "1700000000",
        "user": json.dumps({"id": uid, "first_name": "T"}),
    }
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


# --- auth ----------------------------------------------------------------


async def test_require_owner_accepts_owner():
    user = await A.require_owner("tma " + _init_data(777))
    assert user["id"] == 777


async def test_require_owner_rejects_foreign_and_empty():
    with pytest.raises(HTTPException):
        await A.require_owner("tma " + _init_data(999))
    with pytest.raises(HTTPException):
        await A.require_owner("")


# --- read endpoints ------------------------------------------------------


async def test_status_reports_counts(db):
    await db.add_group(1, "https://t.me/a", "A", 5)
    await db.add_keyword("квартира")
    res = await A.api_status(_=OWNER, db=db)
    assert res["groups"] == 1
    assert res["keywords"] == 1
    assert "next_scan" in res
    assert res["scan_hours"] == 24


async def test_leads_include_group_link(db):
    await db.add_group(1, "https://t.me/a", "A")
    await db.add_find(
        10, 1, "A", "Автор", None, "сдается квартира", "https://t.me/c/1/10"
    )
    res = await A.api_leads(db=db, _=OWNER)
    assert res["leads"][0]["group_link"] == "https://t.me/a"


# --- write endpoints echo to the bot chat --------------------------------


async def test_add_keyword_enqueues_notify(db):
    res = await A.api_add_keyword(FakeReq({"keyword": "квартира"}), _=OWNER, db=db)
    assert res["added"] is True
    assert "квартира" in await db.list_keywords()
    cmd = await db.claim_pending_command()
    assert cmd["type"] == "notify"
    assert "квартира" in cmd["payload"]["text"]


async def test_reset_seen_clears_and_enqueues_notify(db):
    await db.mark_processed(1, 1)
    res = await A.api_reset_seen(_=OWNER, db=db)
    assert res["cleared"] == 1
    cmd = await db.claim_pending_command()
    assert cmd["type"] == "notify"


async def test_export_enqueues_command(db):
    res = await A.api_export(_=OWNER, db=db)
    cmd = await db.claim_pending_command()
    assert cmd["type"] == "export"
    assert res["command_id"] == cmd["id"]
