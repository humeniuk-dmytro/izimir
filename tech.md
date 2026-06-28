# Izimir — Implementation Report

**Project:** Telegram bot for real-estate monitoring (İzmir, Turkey)
**Client:** a private realtor / real-estate agent
**Status:** fully implemented, covered by automated tests, verified on a live account.

> The **product** (bot, Mini App, notifications) is in **Russian** per the client's spec
> (the client is a Russian-speaking realtor). Code, docs and repo are in English.
> Where an early ТЗ draft described different behavior, the differences are marked ⚠️.

---

## 1. Architecture
Two Telethon clients in a single asyncio loop:
- **User client** (phone-number auth) — reads group history, joins/leaves groups, resolves links.
  Needed because the Bot API has no access to group history.
- **Bot client** (token from @BotFather) — owner commands and notifications with inline buttons.

Files: `clients.py`, `__main__.py`.

## 2. Group management
`/add_group <link>` (user account joins via `JoinChannelRequest` / `ImportChatInviteRequest`),
`/remove_group <link>` (leaves via `LeaveChannelRequest`), `/list_groups` (with ✅/❌ flags).
Table `monitored_groups`: `id, group_id (UNIQUE), group_link, group_title, access_hash,
is_active, date_added`.

✅ **Robustness:** the group's `access_hash` is stored, and scanning resolves the group via
`InputPeerChannel(id, access_hash)` → link → bare id. This removes the silent scan failure after
the user account re-authenticates with a fresh session (a common cause of "the bot finds nothing").

## 3. Keyword management
`/add_keyword`, `/remove_keyword`, `/list_keywords`. Table `keywords`: `id, keyword, language,
date_added` (language auto-detected: Cyrillic → `ru`, Latin → `tr`).

⚠️ **Dedup fix.** An early variant relied on `UNIQUE COLLATE NOCASE`, but SQLite NOCASE folds
case **only for ASCII** — Cyrillic/Turkish keywords were not deduplicated (`Снять` and `снять`
were considered different). Dedup and removal now go through the same `fold()` normalization as the
search, so case is handled for all languages.

## 4. Search logic
Twice a day on schedule (`SCAN_TIMES`, default 09:00 and 18:00) plus manual `/scan`. For each active
group: `iter_messages` up to `MESSAGES_LIMIT`, stop when out of the time window, check keywords, skip
already-forwarded, send to the owner, save to DB.

⚠️ **Key search fix (RU/UA/TR).** An early variant compared `keyword in text.lower()`, causing:
1. **Turkish case.** `"SATILIK".lower()` in Python → `"satilik"` (dotted `i`), while the keyword
   `satılık` has `ı` (dotless) — **no match**. Same for `İzmir`/`IZMIR`. Now `fold()` unifies Turkish
   `I/İ/ı/i` and strips diacritics.
2. **Inflections.** `квартира` did not find `квартиру`/`квартиры` (substring mismatch). The keyword is
   now reduced to a **stem** (Russian Snowball for Cyrillic), so `квартира` finds all cases. Turkish
   is agglutinative — the base is already a substring of inflected forms.

✅ **Deep one-off scan:** `/scan 7` scans the last N **days** (history backfill) without changing the
permanent `SCAN_HOURS`.

✅ **Configurable window:** `SCAN_HOURS` in `.env`; shown in the `/scan` reply and in `/help`.

Protection: a shared lock (manual and scheduled scans never overlap); `FloodWaitError` (≤60s → wait,
otherwise skip the group); `ChannelPrivateError` → group deactivated; notification send retry.
Files: `scanner.py`, `scheduler.py`, `normalize.py`.

## 5. Notification format (Russian, per ТЗ §4)
```
📢 Найдено потенциальное объявление
👤 Автор: @username
👥 Группа: Название
🕒 Дата: 21.02.2026 14:30
💬 Сообщение: …
```
Buttons: 🔎 open message (`t.me/c/…` or `t.me/username/…`), 👥 open group, ✉ message the author.
File `formatter.py`. All interface strings live in `texts.py` (Russian).

## 6. Duplicate prevention and lead history
`processed_messages` (`UNIQUE(message_id, group_id)`) — nothing is forwarded twice. `/reset_seen`
clears it (handy for re-sending / testing).

✅ **New:** the `finds` table stores every forwarded lead (author, text, link, time). `/stats` shows
total / today / week / by group. `/export` produces a CSV (UTF-8 BOM for Excel).

## 7. Owner interface
`/help` — number of groups and keywords, total found, last and **next** scan, search window, command
list. ✅ **Slash menu:** the command menu is registered on startup (`SetBotCommandsRequest`) so
Telegram shows hints under "/". ✅ A failed scheduled scan **notifies the owner** (previously only a log).

## 8. Non-functional
- Python 3.12+, Telethon ≥1.36, SQLite (`aiosqlite`), APScheduler, managed with `uv`.
- ⚠️ **Docker fixed:** the image is now reproducible (`uv.lock` + `uv sync --frozen`), a
  `.dockerignore` was added (secrets `.env`, `data/`, sessions, logs stay out of the image), and
  `tzdata` was added (correct timezones/schedule in the slim image). Build verified.
- Logs: console + `logs/izimir.log` + `logs/errors.log` (rotating 5 MB × 3). Owner commands are logged.

## 9. Tests
`uv run pytest -q` — 74 tests: normalization/stemming (RU/UA/TR, Turkish case, reproduction of the
original complaint), scan window and dedup, lead persistence and stats, formatter, `/scan N` parsing,
command menu, Mini App initData auth, and the command queue.

## 10. VPS deployment (Docker)
```bash
cp .env.example .env && nano .env     # API_ID, API_HASH, BOT_TOKEN, OWNER_ID
mkdir data
docker compose run --rm bot           # first run: phone number + code
docker compose up -d                  # 24/7, auto-restart
docker compose logs -f                # logs
```
Without Docker — a systemd service (`uv run python -m izimir`, `Restart=always`).

## 11. Telegram Mini App (web panel)
An in-Telegram web UI (FastAPI + WebApp) next to the bot, sharing the same SQLite (WAL).
- **Tabs:** Leads (feed with search and links), Keywords, Groups, Stats.
- **Auth:** Telegram `initData` validation (HMAC-SHA256 with `bot_token`), owner-only access.
- **Actions needing the user account** (add group, scan) go through the `command_queue`: the web
  enqueues a task, the bot runs it and writes the result, the web polls the status.
- **Free HTTPS:** Caddy (auto Let's Encrypt) + a free **DuckDNS** subdomain, at no cost.
  In `.env`: `WEBAPP_DOMAIN`, `WEBAPP_URL`; `docker compose up -d` brings up `bot` + `web` + `caddy`.
  The Mini App button is set automatically on startup (and/or via @BotFather `/setmenubutton`).
- Files: `src/izimir/webapp/` (app.py, auth.py, static/), `queue_worker.py`, `groups.py`.

## 12. Out of scope (this version)
- v2: Izmir-only geo filter, categorization (buy/sell/rent), Google Sheets export, AI filtering.
