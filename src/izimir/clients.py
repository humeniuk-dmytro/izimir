from __future__ import annotations

from telethon import TelegramClient

from izimir.config import Settings


def make_user_client(settings: Settings) -> TelegramClient:
    return TelegramClient(
        settings.user_session,
        settings.api_id,
        settings.api_hash,
    )


def make_bot_client(settings: Settings) -> TelegramClient:
    return TelegramClient(
        settings.bot_session,
        settings.api_id,
        settings.api_hash,
    )
