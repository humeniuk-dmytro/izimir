"""Тести валідації Telegram initData (Mini App auth)."""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode

from izimir.webapp.auth import owner_from_init_data, validate_init_data

BOT_TOKEN = "123456:TESTTOKEN"
OWNER_ID = 777


def make_init_data(bot_token: str, user_id: int) -> str:
    fields = {
        "auth_date": "1700000000",
        "query_id": "AAABBB",
        "user": json.dumps({"id": user_id, "first_name": "T"}),
    }
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": h})


def test_valid_init_data():
    init = make_init_data(BOT_TOKEN, OWNER_ID)
    parsed = validate_init_data(init, BOT_TOKEN)
    assert parsed is not None
    assert "user" in parsed


def test_tampered_hash_rejected():
    init = make_init_data(BOT_TOKEN, OWNER_ID) + "0"  # ламаємо hash
    assert validate_init_data(init, BOT_TOKEN) is None


def test_wrong_token_rejected():
    init = make_init_data(BOT_TOKEN, OWNER_ID)
    assert validate_init_data(init, "999:OTHER") is None


def test_empty_rejected():
    assert validate_init_data("", BOT_TOKEN) is None


def test_owner_accepted():
    init = make_init_data(BOT_TOKEN, OWNER_ID)
    user = owner_from_init_data(init, BOT_TOKEN, OWNER_ID)
    assert user and user["id"] == OWNER_ID


def test_non_owner_rejected():
    init = make_init_data(BOT_TOKEN, 12345)  # чужий id
    assert owner_from_init_data(init, BOT_TOKEN, OWNER_ID) is None
