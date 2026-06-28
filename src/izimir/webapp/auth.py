"""Telegram Mini App initData validation (HMAC-SHA256).

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Return the parsed initData fields if the signature is valid, else None."""
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calc_hash, received_hash):
        return None
    return parsed


def owner_from_init_data(init_data: str, bot_token: str, owner_id: int) -> dict | None:
    """Validate initData and return the user dict only if it is the owner."""
    parsed = validate_init_data(init_data, bot_token)
    if parsed is None:
        return None
    try:
        user = json.loads(parsed.get("user", "{}"))
    except (ValueError, TypeError):
        return None
    if int(user.get("id", 0)) != owner_id:
        return None
    return user
