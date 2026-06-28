from __future__ import annotations

import json

import aiosqlite

from izimir.normalize import fold

SCHEMA = """CREATE TABLE IF NOT EXISTS monitored_groups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id      INTEGER UNIQUE NOT NULL,
    group_link    TEXT    NOT NULL,
    group_title   TEXT    NOT NULL DEFAULT '',
    access_hash   INTEGER,
    is_active     INTEGER NOT NULL DEFAULT 1,
    date_added    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS keywords (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword    TEXT    UNIQUE NOT NULL COLLATE NOCASE,
    language   TEXT,
    date_added TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processed_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id     INTEGER NOT NULL,
    group_id       INTEGER NOT NULL,
    date_processed TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(message_id, group_id)
);

CREATE TABLE IF NOT EXISTS scan_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    groups_scanned  INTEGER NOT NULL DEFAULT 0,
    messages_found  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS finds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      INTEGER NOT NULL,
    group_id        INTEGER NOT NULL,
    group_title     TEXT NOT NULL DEFAULT '',
    author          TEXT,
    author_username TEXT,
    text            TEXT NOT NULL DEFAULT '',
    msg_link        TEXT,
    found_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(message_id, group_id)
);

CREATE TABLE IF NOT EXISTS command_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'pending',
    result      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        # WAL + busy_timeout: allow the bot and the Mini App web process to
        # read/write the same SQLite file concurrently without "database is
        # locked" errors. (Harmless no-op for an in-memory test DB.)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.executescript(SCHEMA)
        await self._migrate()
        await self._db.commit()

    async def _migrate(self) -> None:
        """Add columns introduced after the first release to existing DBs."""

        async def columns(table: str) -> set[str]:
            cur = await self.db.execute(f"PRAGMA table_info({table})")
            return {r["name"] for r in await cur.fetchall()}

        if "access_hash" not in await columns("monitored_groups"):
            await self.db.execute(
                "ALTER TABLE monitored_groups ADD COLUMN access_hash INTEGER"
            )
        if "language" not in await columns("keywords"):
            await self.db.execute("ALTER TABLE keywords ADD COLUMN language TEXT")

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db

    async def add_group(
        self,
        group_id: int,
        group_link: str,
        group_title: str,
        access_hash: int | None = None,
    ) -> bool:
        try:
            await self.db.execute(
                "INSERT INTO monitored_groups (group_id, group_link, group_title, access_hash) VALUES (?, ?, ?, ?)",
                (group_id, group_link, group_title, access_hash),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_group(self, group_id: int) -> bool:
        cur = await self.db.execute(
            "DELETE FROM monitored_groups WHERE group_id = ?", (group_id,)
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def remove_group_by_link(self, group_link: str) -> bool:
        cur = await self.db.execute(
            "DELETE FROM monitored_groups WHERE group_link = ?", (group_link,)
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def list_groups(self) -> list[dict]:
        cur = await self.db.execute(
            "SELECT group_id, group_link, group_title, is_active FROM monitored_groups ORDER BY date_added"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_active_groups(self) -> list[dict]:
        cur = await self.db.execute(
            "SELECT group_id, group_link, group_title, access_hash FROM monitored_groups WHERE is_active = 1"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def deactivate_group(self, group_id: int) -> None:
        await self.db.execute(
            "UPDATE monitored_groups SET is_active = 0 WHERE group_id = ?", (group_id,)
        )
        await self.db.commit()

    async def add_keyword(self, keyword: str, language: str | None = None) -> bool:
        # SQLite COLLATE NOCASE only folds ASCII, so dedupe Cyrillic/Turkish
        # keywords by case in Python using the same fold() as the search.
        target = fold(keyword)
        if any(fold(k) == target for k in await self.list_keywords()):
            return False
        try:
            await self.db.execute(
                "INSERT INTO keywords (keyword, language) VALUES (?, ?)",
                (keyword, language),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_keyword(self, keyword: str) -> bool:
        target = fold(keyword)
        cur = await self.db.execute("SELECT id, keyword FROM keywords")
        ids = [r["id"] for r in await cur.fetchall() if fold(r["keyword"]) == target]
        if not ids:
            return False
        await self.db.executemany(
            "DELETE FROM keywords WHERE id = ?", [(i,) for i in ids]
        )
        await self.db.commit()
        return True

    async def list_keywords(self) -> list[str]:
        cur = await self.db.execute("SELECT keyword FROM keywords ORDER BY keyword")
        rows = await cur.fetchall()
        return [r["keyword"] for r in rows]

    async def is_processed(self, message_id: int, group_id: int) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM processed_messages WHERE message_id = ? AND group_id = ?",
            (message_id, group_id),
        )
        return await cur.fetchone() is not None

    async def mark_processed(self, message_id: int, group_id: int) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id, group_id) VALUES (?, ?)",
            (message_id, group_id),
        )
        await self.db.commit()

    async def cleanup_processed_messages(self, keep_days: int = 7) -> int:
        """Delete processed_messages older than *keep_days* days.

        Returns the number of rows deleted.
        """
        cur = await self.db.execute(
            "DELETE FROM processed_messages WHERE date_processed < datetime('now', ?)",
            (f"-{keep_days} days",),
        )
        await self.db.commit()
        return cur.rowcount

    async def start_scan(self, started_at: str) -> int:
        cur = await self.db.execute(
            "INSERT INTO scan_log (started_at) VALUES (?)", (started_at,)
        )
        await self.db.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def finish_scan(
        self,
        scan_id: int,
        finished_at: str,
        groups_scanned: int,
        messages_found: int,
        status: str = "ok",
    ) -> None:
        await self.db.execute(
            "UPDATE scan_log SET finished_at = ?, groups_scanned = ?, messages_found = ?, status = ? WHERE id = ?",
            (finished_at, groups_scanned, messages_found, status, scan_id),
        )
        await self.db.commit()

    async def last_scan(self) -> dict | None:
        cur = await self.db.execute("SELECT * FROM scan_log ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
        return dict(row) if row else None

    async def group_count(self) -> int:
        cur = await self.db.execute(
            "SELECT COUNT(*) as cnt FROM monitored_groups WHERE is_active = 1"
        )
        row = await cur.fetchone()
        return row["cnt"] if row else 0

    async def keyword_count(self) -> int:
        cur = await self.db.execute("SELECT COUNT(*) as cnt FROM keywords")
        row = await cur.fetchone()
        return row["cnt"] if row else 0

    async def total_found(self) -> int:
        """Total number of saved leads (consistent with /stats and finds)."""
        cur = await self.db.execute("SELECT COUNT(*) AS total FROM finds")
        row = await cur.fetchone()
        return row["total"] if row else 0

    # --- leads (finds) ---------------------------------------------------

    async def add_find(
        self,
        message_id: int,
        group_id: int,
        group_title: str,
        author: str | None,
        author_username: str | None,
        text: str,
        msg_link: str | None,
    ) -> None:
        """Persist a forwarded lead. Idempotent per (message_id, group_id)."""
        await self.db.execute(
            "INSERT OR IGNORE INTO finds "
            "(message_id, group_id, group_title, author, author_username, text, msg_link) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                message_id,
                group_id,
                group_title,
                author,
                author_username,
                text,
                msg_link,
            ),
        )
        await self.db.commit()

    async def recent_finds(self, limit: int = 1000) -> list[dict]:
        cur = await self.db.execute(
            "SELECT * FROM finds ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def find_stats(self) -> dict:
        async def scalar(query: str) -> int:
            cur = await self.db.execute(query)
            row = await cur.fetchone()
            return row[0] if row else 0

        total = await scalar("SELECT COUNT(*) FROM finds")
        today = await scalar(
            "SELECT COUNT(*) FROM finds WHERE found_at >= datetime('now', 'start of day')"
        )
        week = await scalar(
            "SELECT COUNT(*) FROM finds WHERE found_at >= datetime('now', '-7 days')"
        )
        cur = await self.db.execute(
            "SELECT group_title, COUNT(*) AS c FROM finds "
            "GROUP BY group_id ORDER BY c DESC LIMIT 5"
        )
        by_group = [(r["group_title"], r["c"]) for r in await cur.fetchall()]
        return {"total": total, "today": today, "week": week, "by_group": by_group}

    async def clear_processed(self) -> int:
        """Wipe processed_messages so the next scan re-forwards matches."""
        cur = await self.db.execute("DELETE FROM processed_messages")
        await self.db.commit()
        return cur.rowcount

    # --- command queue (Mini App → bot bridge) ---------------------------

    async def enqueue_command(self, type_: str, payload: dict | None = None) -> int:
        cur = await self.db.execute(
            "INSERT INTO command_queue (type, payload) VALUES (?, ?)",
            (type_, json.dumps(payload or {})),
        )
        await self.db.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def claim_pending_command(self) -> dict | None:
        """Atomically pick the oldest pending command and mark it running."""
        cur = await self.db.execute(
            "SELECT id, type, payload FROM command_queue "
            "WHERE status = 'pending' ORDER BY id LIMIT 1"
        )
        row = await cur.fetchone()
        if row is None:
            return None
        upd = await self.db.execute(
            "UPDATE command_queue SET status = 'running', updated_at = datetime('now') "
            "WHERE id = ? AND status = 'pending'",
            (row["id"],),
        )
        await self.db.commit()
        if upd.rowcount == 0:
            return None  # raced with another worker
        return {
            "id": row["id"],
            "type": row["type"],
            "payload": json.loads(row["payload"]),
        }

    async def finish_command(
        self, command_id: int, status: str, result: str = ""
    ) -> None:
        await self.db.execute(
            "UPDATE command_queue SET status = ?, result = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (status, result, command_id),
        )
        await self.db.commit()

    async def get_command(self, command_id: int) -> dict | None:
        cur = await self.db.execute(
            "SELECT id, type, status, result, created_at "
            "FROM command_queue WHERE id = ?",
            (command_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
