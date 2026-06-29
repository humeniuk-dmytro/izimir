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


async def run_scheduled_scan(
    user_client: TelegramClient,
    bot_client: TelegramClient,
    db: Database,
    settings: Settings,
) -> None:
    """Run a scan on schedule and ALWAYS report the outcome to the owner.

    Reporting even on zero matches is important: otherwise a working schedule
    looks broken (the owner sees nothing in the chat). On error the owner gets
    ``SCAN_FAILED`` instead.
    """
    log.info("Scheduled scan starting")
    try:
        groups, checked, found, errors = await run_scan(
            user_client, bot_client, db, settings
        )
    except Exception:
        log.exception("Scheduled scan failed")
        try:
            await bot_client.send_message(settings.owner_id, texts.SCAN_FAILED)
        except Exception:
            log.exception("Failed to notify owner about scheduled scan failure")
        return

    log.info(
        "Scheduled scan done: %d groups, %d checked, %d found, %d errors",
        groups,
        checked,
        found,
        errors,
    )
    body = texts.SCAN_DONE.format(
        window=f"последние {settings.scan_hours} ч",
        groups=groups,
        checked=checked,
        found=found,
        errors=errors,
    )
    if found == 0 and checked > 0:
        body += "\n\n" + texts.SCAN_NOTHING_NEW
    try:
        await bot_client.send_message(
            settings.owner_id, f"{texts.SCHEDULED_PREFIX}\n{body}"
        )
    except Exception:
        log.exception("Failed to send scheduled scan summary to owner")


def setup_scheduler(
    user_client: TelegramClient,
    bot_client: TelegramClient,
    db: Database,
    settings: Settings,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    for time_str in settings.scan_times:
        hour, minute = time_str.split(":")
        scheduler.add_job(
            run_scheduled_scan,
            CronTrigger(hour=int(hour), minute=int(minute)),
            args=[user_client, bot_client, db, settings],
            id=f"scan_{time_str}",
            replace_existing=True,
        )
        log.info("Scheduled scan at %s (%s)", time_str, settings.timezone)

    nxt = next_scan_time(settings.scan_times, settings.timezone)
    if nxt:
        log.info("Next scheduled scan: %s", nxt.strftime("%Y-%m-%d %H:%M %Z"))

    return scheduler
