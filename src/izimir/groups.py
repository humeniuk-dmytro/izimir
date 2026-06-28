"""Group add/remove logic shared by bot commands and the Mini App queue.

Both /add_group and the Mini App "add group" action need the same
resolve→join→persist flow (it requires the user client), so it lives here.
"""

from __future__ import annotations

import logging
import re

from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel

from izimir.db import Database

log = logging.getLogger(__name__)

_INVITE_RE = re.compile(r"(?:t\.me/\+|t\.me/joinchat/)([a-zA-Z0-9_-]+)")


async def add_group_by_link(
    user_client: TelegramClient, db: Database, link: str
) -> tuple[str, str]:
    """Resolve a link, join with the user account, persist with access_hash.

    Returns ``(status, detail)`` where status is one of
    ``added`` / ``exists`` / ``flood`` / ``error`` and detail is the group
    title (or error text / flood seconds).
    """
    invite_match = _INVITE_RE.search(link)
    try:
        if invite_match:
            invite_hash = invite_match.group(1)
            try:
                updates = await user_client(ImportChatInviteRequest(invite_hash))
                entity = updates.chats[0]
            except UserAlreadyParticipantError:
                entity = await user_client.get_entity(link)
        else:
            entity = await user_client.get_entity(link)
            if isinstance(entity, Channel):
                try:
                    await user_client(JoinChannelRequest(entity))
                except UserAlreadyParticipantError:
                    pass
    except FloodWaitError as e:
        return "flood", str(e.seconds)
    except Exception as e:
        return "error", str(e)

    group_id = entity.id
    access_hash = getattr(entity, "access_hash", None)
    title = (
        getattr(entity, "title", "") or getattr(entity, "username", "") or str(group_id)
    )
    if await db.add_group(group_id, link, title, access_hash):
        return "added", title
    return "exists", title


async def remove_group_by_link(
    user_client: TelegramClient, db: Database, link: str
) -> bool:
    """Remove a group from the DB and leave it with the user account."""
    try:
        entity = await user_client.get_entity(link)
        removed = await db.remove_group(entity.id)
        if removed and isinstance(entity, Channel):
            try:
                await user_client(LeaveChannelRequest(entity))
            except Exception as e:
                log.warning("Failed to leave group %s: %s", link, e)
    except Exception:
        removed = await db.remove_group_by_link(link)
    return removed
