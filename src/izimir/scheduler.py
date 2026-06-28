from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telethon import TelegramClient

from izimir import texts
from izimir.config import Settings
from izimir.db import Database
from izimir.scanner import run_scan

log = logging.getLogger(__name__)


def next_scan_time(scan_times: list[str], tz: str) -> datetime | None:
    """Nearest upcoming scan moment from SCAN_TIMES, in timezone *tz*.

    Pure computation (no APScheduler), so /help can show it. Returns ``None``
    if there are no valid times or the timezone is unavailable.
    """
    try:
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(tz)
    except Exception:
        return None

    now = datetime.now(zone)
    candidates = []
    for time_str in scan_times:
        try:
            hour, minute = (int(x) for x in time_str.split(":"))
        except ValueError:
            continue
        moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if moment <= now:
            moment += timedelta(days=1)
        candidates.append(moment)
    return min(candidates) if candidates else None


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
            groups_scanned, checked, found, errors = await run_scan(
                user_client, bot_client, db, settings
            )
            log.info(
                "Scheduled scan done: %d groups, %d checked, %d found, %d errors",
                groups_scanned,
                checked,
                found,
                errors,
            )
        except Exception:
            log.exception("Scheduled scan failed")
            # Notify the owner so a broken schedule does not go unnoticed.
            try:
                await bot_client.send_message(settings.owner_id, texts.SCAN_FAILED)
            except Exception:
                log.exception("Failed to notify owner about scheduled scan failure")

    for time_str in settings.scan_times:
        hour, minute = time_str.split(":")
        scheduler.add_job(
            scheduled_scan,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id=f"scan_{time_str}",
            replace_existing=True,
        )
        log.info("Scheduled scan at %s (%s)", time_str, settings.timezone)

    nxt = next_scan_time(settings.scan_times, settings.timezone)
    if nxt:
        log.info("Next scheduled scan: %s", nxt.strftime("%Y-%m-%d %H:%M %Z"))

    return scheduler
