from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    bot_token: str
    owner_id: int
    db_path: str
    user_session: str
    bot_session: str
    scan_times: list[str] = field(default_factory=lambda: ["09:00", "18:00"])
    timezone: str = "Europe/Istanbul"
    messages_limit: int = 500
    rate_limit_delay: float = 2.0
    scan_hours: int = 24
    webapp_url: str = ""


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        print(f"ERROR: missing required env variable: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def load_settings() -> Settings:
    load_dotenv()
    scan_raw = os.getenv("SCAN_TIMES", "09:00,18:00")
    return Settings(
        api_id=int(_require("API_ID")),
        api_hash=_require("API_HASH"),
        bot_token=_require("BOT_TOKEN"),
        owner_id=int(_require("OWNER_ID")),
        db_path=os.getenv("DB_PATH", "izimir.db"),
        user_session=os.getenv("USER_SESSION", "user_session"),
        bot_session=os.getenv("BOT_SESSION", "bot_session"),
        scan_times=[t.strip() for t in scan_raw.split(",") if t.strip()],
        timezone=os.getenv("TIMEZONE", "Europe/Istanbul"),
        messages_limit=int(os.getenv("MESSAGES_LIMIT", "500")),
        rate_limit_delay=float(os.getenv("RATE_LIMIT_DELAY", "2.0")),
        scan_hours=int(os.getenv("SCAN_HOURS", "24")),
        webapp_url=os.getenv("WEBAPP_URL", ""),
    )
