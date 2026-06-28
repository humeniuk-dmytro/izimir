# 🏠 Izimir — Telegram Real Estate Monitor

> **Freelance project** · Built for a private real estate agent working in İzmir, Turkey

A Telegram **userbot** that monitors a curated list of Telegram groups for real estate
listings, filters them by keyword (case- and inflection-aware, RU/UA/TR), and forwards
matching messages to the owner with quick-action buttons. Interface language: **Russian**
(per client spec).

---

## ✨ Features

- 📡 **Monitors Telegram groups** — public and private, via the Telegram User API (Telethon)
- 🔍 **Smart keyword matching** — case-insensitive + **stemming**, so `квартира` also finds
  `квартиру`/`квартиры`; correct **Turkish** case folding (`satılık` ↔ `SATILIK`, `İzmir`)
- ⏰ **Scheduled scans** — twice a day via cron (configurable), plus on-demand `/scan`
- 🔭 **Deep on-demand scan** — `/scan 30` widens the window (last N days) for backfill
- 🔁 **Duplicate prevention** — already-seen messages are skipped (`/reset_seen` to re-send)
- 🗂 **Lead history** — every forwarded listing is saved; `/stats` and CSV `/export`
- 🔘 **Inline buttons** — open message · open group · write to author
- 🧭 **Slash-command menu** — Telegram shows command hints under «/»
- 🛡 **Robust** — stored `access_hash` (survives re-login), FloodWait handling, private-group
  auto-deactivation, owner notified if a scheduled scan fails

---

## 🤖 Bot Commands

| Command | Description |
|---|---|
| `/help` | Status: groups, keywords, last/next scan, window |
| `/add_group <link>` · `/remove_group <link>` · `/list_groups` | Manage groups |
| `/add_keyword <word>` · `/remove_keyword <word>` · `/list_keywords` | Manage keywords |
| `/scan [days]` | Scan now; optional window in days (e.g. `/scan 7`) |
| `/stats` | Lead statistics (total / today / week / by group) |
| `/export` | Export all leads as a CSV file |
| `/reset_seen` | Clear "already sent" so the next scan re-forwards matches |

All commands are owner-only (`OWNER_ID`).

---

## 🚀 Quick Start (local)

```bash
cp .env.example .env   # fill in API_ID, API_HASH, BOT_TOKEN, OWNER_ID
uv sync
uv run python -m izimir   # first run asks for phone number + code
```

## 🐳 Deploy with Docker

```bash
cp .env.example .env
mkdir data
docker compose run --rm bot   # first run — Telegram authorization (phone + code)
docker compose up -d          # run 24/7
```

The image is reproducible (`uv.lock`, `uv sync --frozen`); secrets and runtime state are
kept out via `.dockerignore`. SQLite DB and Telethon sessions live in the bind-mounted
`./data`.

---

## ⚙️ Configuration (`.env`)

| Variable | Description |
|---|---|
| `API_ID`, `API_HASH` | Telegram API credentials (my.telegram.org) |
| `BOT_TOKEN` | Bot token from @BotFather |
| `OWNER_ID` | Your numeric Telegram user ID |
| `SCAN_TIMES` | Scheduled scans, e.g. `09:00,18:00` |
| `SCAN_HOURS` | How far back each scan looks, hours (default `24`) |
| `TIMEZONE` | e.g. `Europe/Istanbul` |
| `MESSAGES_LIMIT` | Max messages per group per scan (default `500`) |
| `RATE_LIMIT_DELAY` | Pause between groups, seconds (default `2.0`) |

---

## 🏗 Project Structure

```
src/izimir/
├── __main__.py      # Entry point, logging, startup/shutdown, command menu
├── bot_handlers.py  # All bot commands (owner-only)
├── scanner.py       # Scan logic: window, matching, dedup, lead persistence
├── normalize.py     # fold() + stem_key() — case/inflection-aware matching
├── scheduler.py     # APScheduler cron + next_scan_time()
├── formatter.py     # Notification text, inline buttons, lead fields
├── clients.py       # Telethon client factories (user + bot)
├── db.py            # SQLite: groups, keywords, processed, scan_log, finds
├── texts.py         # All RU interface strings + command menu
└── config.py        # Settings from .env
```

## 🧪 Tests

```bash
uv run pytest -q
```

Covers matching/stemming (RU/UA/TR), the scan window & dedup, lead persistence & stats,
the formatter, and command parsing/menu.

## 📄 License

MIT
