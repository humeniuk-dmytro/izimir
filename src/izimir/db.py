from __future__ import annotations

import aiosqlite

SCHEMA = """CREATE TABLE IF NOT EXISTS monitored_groups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id      INTEGER UNIQUE NOT NULL,
    group_link    TEXT    NOT NULL,
    group_title   TEXT    NOT NULL DEFAULT '',
    is_active     INTEGER NOT NULL DEFAULT 1,
    date_added    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS keywords (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT    UNIQUE NOT NULL COLLATE NOCASE
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
"""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db

    async def add_group(self, group_id: int, group_link: str, group_title: str) -> bool:
        try:
            await self.db.execute(
                "INSERT INTO monitored_groups (group_id, group_link, group_title) VALUES (?, ?, ?)",
                (group_id, group_link, group_title),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_group(self, group_id: int) -> bool:
        cur = await self.db.execute("DELETE FROM monitored_groups WHERE group_id = ?", (group_id,))
        await self.db.commit()
        return cur.rowcount > 0

    async def remove_group_by_link(self, group_link: str) -> bool:
        cur = await self.db.execute("DELETE FROM monitored_groups WHERE group_link = ?", (group_link,))
        await self.db.commit()
        return cur.rowcount > 0

    async def list_groups(self) -> list[dict]:
        cur = await self.db.execute("SELECT group_id, group_link, group_title, is_active FROM monitored_groups ORDER BY date_added")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_active_groups(self) -> list[dict]:
        cur = await self.db.execute("SELECT group_id, group_link, group_title FROM monitored_groups WHERE is_active = 1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def deactivate_group(self, group_id: int) -> None:
        await self.db.execute("UPDATE monitored_groups SET is_active = 0 WHERE group_id = ?", (group_id,))
        await self.db.commit()

    async def add_keyword(self, keyword: str) -> bool:
        try:
            await self.db.execute("INSERT INTO keywords (keyword) VALUES (?)", (keyword,))
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_keyword(self, keyword: str) -> bool:
        cur = await self.db.execute("DELETE FROM keywords WHERE keyword = ? COLLATE NOCASE", (keyword,))
        await self.db.commit()
        return cur.rowcount > 0

    async def list_keywords(self) -> list[str]:
        cur = await self.db.execute("SELECT keyword FROM keywords ORDER BY keyword")
        rows = await cur.fetchall()
        return [r["keyword"] for r in rows]

    async def is_processed(self, message_id: int, group_id: int) -> bool:
        cur = await self.db.execute("SELECT 1 FROM processed_messages WHERE message_id = ? AND group_id = ?", (message_id, group_id))
        return await cur.fetchone() is not None

    async def mark_processed(self, message_id: int, group_id: int) -> None:
        await self.db.execute("INSERT OR IGNORE INTO processed_messages (message_id, group_id) VALUES (?, ?)", (message_id, group_id))
        await self.db.commit()

    async def start_scan(self, started_at: str) -> int:
        cur = await self.db.execute("INSERT INTO scan_log (started_at) VALUES (?)", (started_at,))
        await self.db.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def finish_scan(self, scan_id: int, finished_at: str, groups_scanned: int, messages_found: int, status: str = "ok") -> None:
        await self.db.execute("UPDATE scan_log SET finished_at = ?, groups_scanned = ?, messages_found = ?, status = ? WHERE id = ?", (finished_at, groups_scanned, messages_found, status, scan_id))
        await self.db.commit()

    async def last_scan(self) -> dict | None:
        cur = await self.db.execute("SELECT * FROM scan_log ORDER BY id DESC LIMIT 1")
        row = await cur.fetchone()
        return dict(row) if row else None

    async def group_count(self) -> int:
        cur = await self.db.execute("SELECT COUNT(*) as cnt FROM monitored_groups WHERE is_active = 1")
        row = await cur.fetchone()
        return row["cnt"] if row else 0

    async def keyword_count(self) -> int:
        cur = await self.db.execute("SELECT COUNT(*) as cnt FROM keywords")
        row = await cur.fetchone()
        return row["cnt"] if row else 0
