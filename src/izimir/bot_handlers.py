from __future__ import annotations

import asyncio
import functools
import logging
import re

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel

from izimir.config import Settings
from izimir.db import Database
from izimir.scanner import run_scan, is_scanning

log = logging.getLogger(__name__)


def register_handlers(
    bot_client: TelegramClient,
    user_client: TelegramClient,
    db: Database,
    settings: Settings,
) -> None:
    def owner_only(func):
        @functools.wraps(func)
        async def wrapper(event):
            if event.sender_id != settings.owner_id:
                return
            return await func(event)
        return wrapper

    @bot_client.on(events.NewMessage(pattern=r"^/start$"))
    @owner_only
    async def cmd_start(event):
        await event.respond(
            "👋 Hi! I'm a real estate monitoring bot for İzmir.\n"
            "Use /help to see available commands."
        )

    @bot_client.on(events.NewMessage(pattern=r"^/help$"))
    @owner_only
    async def cmd_help(event):
        gc = await db.group_count()
        kc = await db.keyword_count()
        last = await db.last_scan()
        last_info = "—"
        if last:
            last_info = f"{last['started_at']}, found: {last['messages_found']}, status: {last['status']}"

        await event.respond(
            f"📊 **Status**\n"
            f"Groups: {gc}\n"
            f"Keywords: {kc}\n"
            f"Last scan: {last_info}\n\n"
            f"**Commands:**\n"
            f"/add_group <link> — add a group\n"
            f"/remove_group <link> — remove a group\n"
            f"/list_groups — list all groups\n"
            f"/add_keyword <word> — add a keyword\n"
            f"/remove_keyword <word> — remove a keyword\n"
            f"/list_keywords — list all keywords\n"
            f"/scan — run scan now",
            parse_mode="md",
        )

    @bot_client.on(events.NewMessage(pattern=r"^/add_group (.+)"))
    @owner_only
    async def cmd_add_group(event):
        link = event.pattern_match.group(1).strip()
        invite_match = re.search(r'(?:t\.me/\+|t\.me/joinchat/)([a-zA-Z0-9_-]+)', link)

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
            await event.respond(f"⏳ Flood wait {e.seconds}s, try again later.")
            return
        except Exception as e:
            await event.respond(f"❌ Could not find or join the group: {e}")
            return

        group_id = entity.id
        title = getattr(entity, "title", "") or getattr(entity, "username", "") or str(group_id)

        if await db.add_group(group_id, link, title):
            await event.respond(f"✅ Group added (user account joined): {title}")
        else:
            await event.respond(f"ℹ️ Group already in the list: {title}")

    @bot_client.on(events.NewMessage(pattern=r"^/remove_group (.+)"))
    @owner_only
    async def cmd_remove_group(event):
        link = event.pattern_match.group(1).strip()

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

        if removed:
            await event.respond("✅ Group removed, user account left the group.")
        else:
            await event.respond("❌ Group not found in the list.")

    @bot_client.on(events.NewMessage(pattern=r"^/list_groups$"))
    @owner_only
    async def cmd_list_groups(event):
        groups = await db.list_groups()
        if not groups:
            await event.respond("Group list is empty.")
            return
        lines = []
        for g in groups:
            status = "✅" if g["is_active"] else "❌"
            lines.append(f"{status} {g['group_title']} — {g['group_link']}")
        await event.respond("\n".join(lines))

    @bot_client.on(events.NewMessage(pattern=r"^/add_keyword (.+)"))
    @owner_only
    async def cmd_add_keyword(event):
        kw = event.pattern_match.group(1).strip()
        if await db.add_keyword(kw):
            await event.respond(f"✅ Keyword added: {kw}")
        else:
            await event.respond(f"ℹ️ Keyword already exists: {kw}")

    @bot_client.on(events.NewMessage(pattern=r"^/remove_keyword (.+)"))
    @owner_only
    async def cmd_remove_keyword(event):
        kw = event.pattern_match.group(1).strip()
        if await db.remove_keyword(kw):
            await event.respond(f"✅ Keyword removed: {kw}")
        else:
            await event.respond(f"❌ Keyword not found: {kw}")

    @bot_client.on(events.NewMessage(pattern=r"^/list_keywords$"))
    @owner_only
    async def cmd_list_keywords(event):
        keywords = await db.list_keywords()
        if not keywords:
            await event.respond("Keyword list is empty.")
            return
        await event.respond("🔑 Keywords:\n" + "\n".join(f"• {kw}" for kw in keywords))

    @bot_client.on(events.NewMessage(pattern=r"^/scan$"))
    @owner_only
    async def cmd_scan(event):
        if is_scanning():
            await event.respond("⏳ Scan already in progress…")
            return
        await event.respond("🔍 Starting scan…")
        try:
            groups_scanned, messages_found = await run_scan(
                user_client, bot_client, db, settings
            )
            await event.respond(
                f"✅ Scan complete.\n"
                f"Groups scanned: {groups_scanned}\n"
                f"Messages found: {messages_found}"
            )
        except Exception as e:
            log.exception("Scan error")
            await event.respond(f"❌ Scan error: {e}")
