from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telethon import TelegramClient

from izimir.config import Settings
from izimir.db import Database
from izimir.scanner import run_scan

log = logging.getLogger(__name__)


def setup_scheduler(
    user_client: TelegramClient,
    bot_client: TelegramClient,
    db: Database,
    settings: Settings,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    async def scheduled_scan() -> None:
        log.info("Scheduled scan starting")
        try:
            groups_scanned, messages_found = await run_scan(
                user_client, bot_client, db, settings
            )
            log.info(
                "Scheduled scan done: %d groups, %d messages",
                groups_scanned, messages_found,
            )
        except Exception:
            log.exception("Scheduled scan failed")

    for time_str in settings.scan_times:
        hour, minute = time_str.split(":")
        scheduler.add_job(
            scheduled_scan,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id=f"scan_{time_str}",
            replace_existing=True,
        )
        log.info("Scheduled scan at %s (%s)", time_str, settings.timezone)

    return scheduler
