from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, FloodWaitError
from telethon.tl.types import Channel, InputPeerChannel

from izimir.config import Settings
from izimir.db import Database
from izimir.formatter import format_found_message, lead_fields
from izimir.normalize import fold, stem_key

log = logging.getLogger(__name__)

_scan_lock = asyncio.Lock()

__all__ = ["fold", "stem_key", "text_matches", "is_scanning", "run_scan"]


def text_matches(text: str, keyword_stems: list[str]) -> bool:
    """True if folded *text* contains any of the *keyword_stems*.

    Stems come from :func:`stem_key`, so inflected forms match too
    («квартира» key finds «квартиру»).
    """
    folded = fold(text)
    return any(stem in folded for stem in keyword_stems)


def is_scanning() -> bool:
    """Return True if a scan is currently in progress."""
    return _scan_lock.locked()


async def _resolve_entity(user_client: TelegramClient, group: dict):
    """Resolve a monitored group to a usable entity, robustly.

    Order: stored access_hash (no session cache needed) → link/username
    (stable for public groups) → bare id (relies on session cache). The
    bare-id path is the fragile one that silently breaks after the user
    re-authenticates with a fresh session, so it is the last resort.
    """
    gid = group["group_id"]
    access_hash = group.get("access_hash")
    link = group.get("group_link")

    if access_hash:
        try:
            return await user_client.get_entity(InputPeerChannel(gid, access_hash))
        except Exception as e:
            log.debug("Resolve via access_hash failed for %s: %s", gid, e)

    if link:
        try:
            return await user_client.get_entity(link)
        except Exception as e:
            log.debug("Resolve via link failed for %s (%s): %s", gid, link, e)

    return await user_client.get_entity(gid)


async def run_scan(
    user_client: TelegramClient,
    bot_client: TelegramClient,
    db: Database,
    settings: Settings,
    hours_override: int | None = None,
) -> tuple[int, int, int, int]:
    """Run a full scan.

    Returns ``(groups_scanned, messages_checked, found, errors)``:
    groups successfully iterated, messages inspected within the time window,
    new listings forwarded to the owner, and groups that errored.

    *hours_override* widens/narrows the time window for a one-off deep scan
    (e.g. ``/scan 720``); when ``None`` the configured ``SCAN_HOURS`` is used.

    Uses a module-level lock to prevent concurrent scans
    (manual /scan vs scheduled scan).
    """
    if _scan_lock.locked():
        log.warning("Scan already in progress, skipping")
        return 0, 0, 0, 0

    async with _scan_lock:
        now_str = datetime.now(timezone.utc).isoformat()
        scan_id = await db.start_scan(now_str)

        groups = await db.get_active_groups()
        keywords = await db.list_keywords()

        if not groups or not keywords:
            await db.finish_scan(
                scan_id, datetime.now(timezone.utc).isoformat(), 0, 0, "ok"
            )
            return 0, 0, 0, 0

        keyword_stems = [stem_key(kw) for kw in keywords]
        window_hours = (
            hours_override if hours_override is not None else settings.scan_hours
        )
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

        groups_scanned = 0
        messages_checked = 0
        found = 0
        errors = 0

        try:
            for group in groups:
                group_id = group["group_id"]
                group_title = group["group_title"]
                group_link = group["group_link"]

                try:
                    entity = await _resolve_entity(user_client, group)
                    group_username = (
                        entity.username if isinstance(entity, Channel) else None
                    )

                    async for msg in user_client.iter_messages(
                        entity,
                        limit=settings.messages_limit,
                    ):
                        if msg.date and msg.date < since:
                            break

                        messages_checked += 1

                        if not msg.text:
                            continue

                        if not text_matches(msg.text, keyword_stems):
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
                                    msg.id,
                                    group_id,
                                    e2,
                                )
                                continue

                        await db.mark_processed(msg.id, group_id)
                        try:
                            await db.add_find(
                                **lead_fields(
                                    msg, group_title, group_username, group_id
                                )
                            )
                        except Exception:
                            log.exception("Failed to persist lead for msg %s", msg.id)
                        found += 1

                    groups_scanned += 1

                except ChannelPrivateError:
                    log.warning(
                        "Group %s (%s) is private/inaccessible, deactivating",
                        group_title,
                        group_link,
                    )
                    await db.deactivate_group(group_id)
                    errors += 1
                except FloodWaitError as e:
                    if e.seconds <= 60:
                        log.warning("FloodWait %ds, sleeping", e.seconds)
                        await asyncio.sleep(e.seconds)
                    else:
                        log.warning(
                            "FloodWait %ds too long, skipping group %s",
                            e.seconds,
                            group_title,
                        )
                    errors += 1
                except Exception:
                    log.exception(
                        "Error scanning group %s (%s)", group_title, group_link
                    )
                    errors += 1

                await asyncio.sleep(settings.rate_limit_delay)

        except Exception:
            log.exception("Scan failed")
            await db.finish_scan(
                scan_id,
                datetime.now(timezone.utc).isoformat(),
                groups_scanned,
                found,
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
            found,
            "ok",
        )
        return groups_scanned, messages_checked, found, errors
