from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from izimir.config import load_settings
from izimir.clients import make_user_client, make_bot_client
from izimir.db import Database
from izimir.bot_handlers import register_handlers, set_bot_commands, set_menu_button
from izimir.queue_worker import run_queue_worker
from izimir.scheduler import setup_scheduler

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DIR = Path("logs")


def _setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(console)

    file_all = RotatingFileHandler(
        LOG_DIR / "izimir.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_all.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_all)

    file_err = RotatingFileHandler(
        LOG_DIR / "errors.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_err.setLevel(logging.ERROR)
    file_err.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_err)


_setup_logging()
log = logging.getLogger("izimir")


async def main() -> None:
    settings = load_settings()
    log.info("Settings loaded, db=%s", settings.db_path)

    # Ensure parent dirs for the DB and session files exist (fixes startup
    # crash when DB_PATH=data/... but the data/ dir was never created).
    for path in (settings.db_path, settings.user_session, settings.bot_session):
        parent = Path(path).parent
        if parent != Path("."):
            parent.mkdir(parents=True, exist_ok=True)

    db = Database(settings.db_path)
    await db.connect()
    log.info("Database ready")

    user_client = make_user_client(settings)
    bot_client = make_bot_client(settings)

    await user_client.start()
    log.info("User client started")

    await bot_client.start(bot_token=settings.bot_token)
    log.info("Bot client started")

    register_handlers(bot_client, user_client, db, settings)
    await set_bot_commands(bot_client)
    log.info("Bot handlers registered, command menu set")

    scheduler = setup_scheduler(user_client, bot_client, db, settings)
    scheduler.start()
    log.info("Scheduler started with scan times: %s", settings.scan_times)

    worker_task = asyncio.create_task(
        run_queue_worker(user_client, bot_client, db, settings)
    )
    if settings.webapp_url:
        await set_menu_button(bot_client, settings.webapp_url)
        log.info("Mini App menu button set: %s", settings.webapp_url)

    log.info("Bot is running. Press Ctrl+C to stop.")
    try:
        await bot_client.run_until_disconnected()
    finally:
        worker_task.cancel()
        scheduler.shutdown(wait=False)
        await db.close()
        log.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
