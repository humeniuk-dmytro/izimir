"""Background worker that executes Mini App commands needing the user client.

The web process can't run telethon, so it enqueues commands (add_group / scan /
remove_group) into ``command_queue``; this worker (in the bot process) polls and
runs them through the same helpers the bot commands use.
"""

from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient

from izimir.config import Settings
from izimir.db import Database
from izimir.groups import add_group_by_link, remove_group_by_link
from izimir.scanner import run_scan

log = logging.getLogger(__name__)


async def _execute(
    cmd: dict,
    user_client: TelegramClient,
    bot_client: TelegramClient,
    db: Database,
    settings: Settings,
) -> tuple[str, str]:
    ctype = cmd["type"]
    payload = cmd["payload"]

    if ctype == "scan":
        days = payload.get("days")
        hours = int(days) * 24 if days else None
        groups, checked, found, errors = await run_scan(
            user_client, bot_client, db, settings, hours_override=hours
        )
        return "done", f"найдено: {found}, проверено: {checked}, ошибок: {errors}"

    if ctype == "add_group":
        status, detail = await add_group_by_link(user_client, db, payload["link"])
        ok = status in ("added", "exists")
        return ("done" if ok else "error"), f"{status}: {detail}"

    if ctype == "remove_group":
        removed = await remove_group_by_link(user_client, db, payload["link"])
        return ("done", "удалена") if removed else ("error", "не найдена")

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
