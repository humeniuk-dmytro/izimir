from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.tl.types import Channel

from izimir.config import Settings
from izimir.db import Database
from izimir.formatter import format_found_message

log = logging.getLogger(__name__)

_scan_lock = asyncio.Lock()


def is_scanning() -> bool:
    """Return True if a scan is currently in progress."""
    return _scan_lock.locked()


async def run_scan(
    user_client: TelegramClient,
    bot_client: TelegramClient,
    db: Database,
    settings: Settings,
) -> tuple[int, int]:
    """Run a full scan. Returns (groups_scanned, messages_found).

    Uses a module-level lock to prevent concurrent scans
    (manual /scan vs scheduled scan).
    """
    if _scan_lock.locked():
        log.warning("Scan already in progress, skipping")
        return 0, 0

    async with _scan_lock:
        now_str = datetime.now(timezone.utc).isoformat()
        scan_id = await db.start_scan(now_str)

        groups = await db.get_active_groups()
        keywords = await db.list_keywords()

        if not groups or not keywords:
            await db.finish_scan(scan_id, datetime.now(timezone.utc).isoformat(), 0, 0, "ok")
            return 0, 0

        keywords_lower = [kw.lower() for kw in keywords]
        since = datetime.now(timezone.utc) - timedelta(hours=24)

        groups_scanned = 0
        messages_found = 0

        try:
            for group in groups:
                group_id = group["group_id"]
                group_title = group["group_title"]
                group_link = group["group_link"]

                try:
                    entity = await user_client.get_entity(group_id)
                    group_username = entity.username if isinstance(entity, Channel) else None

                    async for msg in user_client.iter_messages(
                        entity,
                        limit=settings.messages_limit,
                    ):
                        if msg.date and msg.date < since:
                            break

                        if not msg.text:
                            continue

                        text_lower = msg.text.lower()
                        if not any(kw in text_lower for kw in keywords_lower):
                            continue

                        if await db.is_processed(msg.id, group_id):
                            continue

                        body, buttons = format_found_message(
                            msg, group_title, group_username, group_id, group_link
                        )

                        try:
                            await bot_client.send_message(
                                settings.owner_id,
                                body,
                                buttons=buttons,
                                parse_mode="md",
                            )
                        except Exception:
                            await asyncio.sleep(1)
                            try:
                                await bot_client.send_message(
                                    settings.owner_id,
                                    body,
                                    buttons=buttons,
                                    parse_mode="md",
                                )
                            except Exception as e2:
                                log.error(
                                    "Failed to notify owner about msg %s in %s: %s",
                                    msg.id, group_id, e2,
                                )
                                continue

                        await db.mark_processed(msg.id, group_id)
                        messages_found += 1

                    groups_scanned += 1

                except ChannelPrivateError:
                    log.warning(
                        "Group %s (%s) is private/inaccessible, deactivating",
                        group_title, group_link,
                    )
                    await db.deactivate_group(group_id)
                    groups_scanned += 1
                except FloodWaitError as e:
                    if e.seconds <= 60:
                        log.warning("FloodWait %ds, sleeping", e.seconds)
                        await asyncio.sleep(e.seconds)
                    else:
                        log.warning(
                            "FloodWait %ds too long, skipping group %s",
                            e.seconds, group_title,
                        )
                except Exception:
                    log.exception("Error scanning group %s (%s)", group_title, group_link)

                await asyncio.sleep(settings.rate_limit_delay)

        except Exception:
            log.exception("Scan failed")
            await db.finish_scan(
                scan_id,
                datetime.now(timezone.utc).isoformat(),
                groups_scanned,
                messages_found,
                "error",
            )
            raise

        deleted = await db.cleanup_processed_messages(keep_days=7)
        if deleted:
            log.info("Cleaned up %d old processed_messages entries", deleted)

        await db.finish_scan(
            scan_id,
            datetime.now(timezone.utc).isoformat(),
            groups_scanned,
            messages_found,
            "ok",
        )
        return groups_scanned, messages_found
