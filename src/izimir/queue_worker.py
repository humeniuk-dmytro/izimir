"""Background worker that executes Mini App commands needing the user client.

The web process can't run telethon, so it enqueues commands (add_group / scan /
remove_group / export / notify) into ``command_queue``; this worker (in the bot
process) polls and runs them through the same helpers the bot commands use.

Every command also echoes its outcome to the owner's chat, so an action taken in
the Mini App looks just like running the matching bot command by hand.
"""

from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient

from izimir import texts
from izimir.config import Settings
from izimir.db import Database
from izimir.exporter import leads_csv
from izimir.groups import add_group_by_link, remove_group_by_link
from izimir.scanner import run_scan

log = logging.getLogger(__name__)


def _scan_summary(days, groups, checked, found, errors) -> str:
    window = f"последние {days} дн." if days else None
    body = texts.SCAN_DONE.format(
        window=window or "окно по умолчанию",
        groups=groups,
        checked=checked,
        found=found,
        errors=errors,
    )
    if found == 0 and checked > 0:
        body += "\n\n" + texts.SCAN_NOTHING_NEW
    return f"{texts.MINIAPP_ACTION}\n{body}"


def _add_group_summary(status: str, detail: str) -> str:
    if status == "added":
        return texts.GROUP_ADDED.format(title=detail)
    if status == "exists":
        return texts.GROUP_EXISTS.format(title=detail)
    if status == "flood":
        return texts.GROUP_FLOOD.format(seconds=detail)
    return texts.GROUP_JOIN_FAILED.format(error=detail)


async def _execute(
    cmd: dict,
    user_client: TelegramClient,
    bot_client: TelegramClient,
    db: Database,
    settings: Settings,
) -> tuple[str, str]:
    """Run a queued command and notify the owner. Returns (status, result)."""
    ctype = cmd["type"]
    payload = cmd["payload"]
    owner = settings.owner_id

    if ctype == "scan":
        days = payload.get("days")
        hours = int(days) * 24 if days else None
        groups, checked, found, errors = await run_scan(
            user_client, bot_client, db, settings, hours_override=hours
        )
        await bot_client.send_message(
            owner, _scan_summary(days, groups, checked, found, errors)
        )
        return "done", f"найдено: {found}, проверено: {checked}, ошибок: {errors}"

    if ctype == "add_group":
        status, detail = await add_group_by_link(user_client, db, payload["link"])
        ok = status in ("added", "exists")
        await bot_client.send_message(owner, _add_group_summary(status, detail))
        return ("done" if ok else "error"), f"{status}: {detail}"

    if ctype == "remove_group":
        removed = await remove_group_by_link(user_client, db, payload["link"])
        await bot_client.send_message(
            owner, texts.GROUP_REMOVED if removed else texts.GROUP_NOT_FOUND
        )
        return ("done", "удалена") if removed else ("error", "не найдена")

    if ctype == "export":
        finds = await db.recent_finds(limit=5000)
        if not finds:
            await bot_client.send_message(owner, texts.EXPORT_EMPTY)
            return "done", "пусто"
        await bot_client.send_file(
            owner,
            leads_csv(finds),
            caption=texts.EXPORT_CAPTION.format(count=len(finds)),
        )
        return "done", f"экспорт отправлен в чат: {len(finds)}"

    if ctype == "notify":
        text = payload.get("text") or ""
        if text:
            await bot_client.send_message(owner, text)
        return "done", ""

    return "error", f"unknown command: {ctype}"


async def run_queue_worker(
    user_client: TelegramClient,
    bot_client: TelegramClient,
    db: Database,
    settings: Settings,
    interval: float = 5.0,
) -> None:
    log.info("Command queue worker started (interval %.0fs)", interval)
    while True:
        try:
            cmd = await db.claim_pending_command()
            if cmd is None:
                await asyncio.sleep(interval)
                continue
            log.info("Processing queued command #%s: %s", cmd["id"], cmd["type"])
            try:
                status, result = await _execute(
                    cmd, user_client, bot_client, db, settings
                )
            except Exception as e:
                log.exception("Queued command #%s failed", cmd["id"])
                status, result = "error", str(e)
            await db.finish_command(cmd["id"], status, result)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Queue worker loop error")
            await asyncio.sleep(interval)
