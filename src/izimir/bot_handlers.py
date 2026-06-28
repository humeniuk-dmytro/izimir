from __future__ import annotations

import csv
import functools
import io
import logging
import re

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault, Channel

from izimir import texts
from izimir.config import Settings
from izimir.db import Database
from izimir.scanner import is_scanning, run_scan
from izimir.scheduler import next_scan_time

log = logging.getLogger(__name__)


async def set_bot_commands(bot_client: TelegramClient) -> None:
    """Register the slash-command menu so Telegram shows hints under «/»."""
    commands = [BotCommand(command=c, description=d) for c, d in texts.BOT_COMMANDS]
    await bot_client(
        SetBotCommandsRequest(
            scope=BotCommandScopeDefault(), lang_code="", commands=commands
        )
    )


def _fmt_local(iso: str, tz: str) -> str:
    """ISO timestamp → 'дд.мм.гггг чч:хх' in the given timezone."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        return (
            datetime.fromisoformat(iso)
            .astimezone(ZoneInfo(tz))
            .strftime("%d.%m.%Y %H:%M")
        )
    except Exception:
        return iso


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
                log.info("Ignored command from non-owner %s", event.sender_id)
                return
            log.info("Owner command: %s", (event.raw_text or "").splitlines()[0])
            return await func(event)

        return wrapper

    @bot_client.on(events.NewMessage(pattern=r"^/start$"))
    @owner_only
    async def cmd_start(event):
        await event.respond(texts.START)

    @bot_client.on(events.NewMessage(pattern=r"^/help$"))
    @owner_only
    async def cmd_help(event):
        gc = await db.group_count()
        kc = await db.keyword_count()
        total = await db.total_found()
        last = await db.last_scan()
        last_info = texts.LAST_SCAN_NONE
        if last:
            last_info = texts.LAST_SCAN.format(
                started_at=_fmt_local(last["started_at"], settings.timezone),
                found=last["messages_found"],
                status=last["status"],
            )

        nxt = next_scan_time(settings.scan_times, settings.timezone)
        next_info = nxt.strftime("%d.%m %H:%M") if nxt else texts.NEXT_SCAN_NONE

        await event.respond(
            texts.HELP.format(
                groups=gc,
                keywords=kc,
                total_found=total,
                last_scan=last_info,
                next_scan=next_info,
                scan_hours=settings.scan_hours,
            ),
            parse_mode="md",
        )

    @bot_client.on(events.NewMessage(pattern=r"^/add_group (.+)"))
    @owner_only
    async def cmd_add_group(event):
        link = event.pattern_match.group(1).strip()
        invite_match = re.search(r"(?:t\.me/\+|t\.me/joinchat/)([a-zA-Z0-9_-]+)", link)

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
            await event.respond(texts.GROUP_FLOOD.format(seconds=e.seconds))
            return
        except Exception as e:
            await event.respond(texts.GROUP_JOIN_FAILED.format(error=e))
            return

        group_id = entity.id
        access_hash = getattr(entity, "access_hash", None)
        title = (
            getattr(entity, "title", "")
            or getattr(entity, "username", "")
            or str(group_id)
        )

        if await db.add_group(group_id, link, title, access_hash):
            await event.respond(texts.GROUP_ADDED.format(title=title))
        else:
            await event.respond(texts.GROUP_EXISTS.format(title=title))

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
            await event.respond(texts.GROUP_REMOVED)
        else:
            await event.respond(texts.GROUP_NOT_FOUND)

    @bot_client.on(events.NewMessage(pattern=r"^/list_groups$"))
    @owner_only
    async def cmd_list_groups(event):
        groups = await db.list_groups()
        if not groups:
            await event.respond(texts.GROUPS_EMPTY)
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
        language = texts.detect_language(kw)
        if await db.add_keyword(kw, language):
            await event.respond(texts.KEYWORD_ADDED.format(keyword=kw))
        else:
            await event.respond(texts.KEYWORD_EXISTS.format(keyword=kw))

    @bot_client.on(events.NewMessage(pattern=r"^/remove_keyword (.+)"))
    @owner_only
    async def cmd_remove_keyword(event):
        kw = event.pattern_match.group(1).strip()
        if await db.remove_keyword(kw):
            await event.respond(texts.KEYWORD_REMOVED.format(keyword=kw))
        else:
            await event.respond(texts.KEYWORD_NOT_FOUND.format(keyword=kw))

    @bot_client.on(events.NewMessage(pattern=r"^/list_keywords$"))
    @owner_only
    async def cmd_list_keywords(event):
        keywords = await db.list_keywords()
        if not keywords:
            await event.respond(texts.KEYWORDS_EMPTY)
            return
        await event.respond(
            texts.KEYWORDS_HEADER + "\n" + "\n".join(f"• {kw}" for kw in keywords)
        )

    @bot_client.on(events.NewMessage(pattern=r"^/scan(?:\s+(\d+))?$"))
    @owner_only
    async def cmd_scan(event):
        if is_scanning():
            await event.respond(texts.SCAN_IN_PROGRESS)
            return
        arg = event.pattern_match.group(1)
        if arg:
            # аргумент — число ДНЕЙ; cap до года, чтобы избежать переполнения
            days = min(int(arg), 365)
            hours_override = days * 24
            window = f"последние {days} дн."
        else:
            hours_override = None
            window = f"последние {settings.scan_hours} ч"
        await event.respond(texts.SCAN_STARTED)
        try:
            groups_scanned, checked, found, errors = await run_scan(
                user_client, bot_client, db, settings, hours_override=hours_override
            )
            log.info(
                "Manual scan (%s): groups=%d checked=%d found=%d errors=%d",
                window,
                groups_scanned,
                checked,
                found,
                errors,
            )
            body = texts.SCAN_DONE.format(
                window=window,
                groups=groups_scanned,
                checked=checked,
                found=found,
                errors=errors,
            )
            if found == 0 and checked > 0:
                body += "\n\n" + texts.SCAN_NOTHING_NEW
            await event.respond(body)
        except Exception as e:
            log.exception("Scan error")
            await event.respond(texts.SCAN_ERROR.format(error=e))

    @bot_client.on(events.NewMessage(pattern=r"^/stats$"))
    @owner_only
    async def cmd_stats(event):
        s = await db.find_stats()
        if not s["total"]:
            await event.respond(texts.STATS_EMPTY)
            return
        body = texts.STATS.format(total=s["total"], today=s["today"], week=s["week"])
        if s["by_group"]:
            rows = "\n".join(
                texts.STATS_BY_GROUP_ROW.format(title=t, count=c)
                for t, c in s["by_group"]
            )
            body += texts.STATS_BY_GROUP_HEADER + "\n" + rows
        await event.respond(body)

    @bot_client.on(events.NewMessage(pattern=r"^/export$"))
    @owner_only
    async def cmd_export(event):
        finds = await db.recent_finds(limit=5000)
        if not finds:
            await event.respond(texts.EXPORT_EMPTY)
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["found_at", "group", "author", "username", "text", "link"])
        for f in reversed(finds):  # хронологический порядок
            writer.writerow(
                [
                    f["found_at"],
                    f["group_title"],
                    f["author"] or "",
                    f["author_username"] or "",
                    f["text"],
                    f["msg_link"] or "",
                ]
            )
        # utf-8-sig: BOM, чтобы Excel корректно открыл кириллицу
        bio = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        bio.name = "izimir_leads.csv"
        await bot_client.send_file(
            settings.owner_id,
            bio,
            caption=texts.EXPORT_CAPTION.format(count=len(finds)),
        )

    @bot_client.on(events.NewMessage(pattern=r"^/reset_seen$"))
    @owner_only
    async def cmd_reset_seen(event):
        count = await db.clear_processed()
        await event.respond(texts.RESET_DONE.format(count=count))
