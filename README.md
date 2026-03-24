# 🏠 Izimir — Telegram Real Estate Monitor

> **Freelance project** · Built for a private real estate agent working in İzmir, Turkey

A Telegram **userbot** that automatically monitors a curated list of Telegram groups for real estate listings, filters them by keyword, and forwards matching messages to the owner with quick-action buttons.

---

## ✨ Features

- 📡 **Monitors Telegram groups** — public and private, via Telegram User API (Telethon)
- 🔍 **Keyword filtering** — multilingual support (Russian / Ukrainian / Turkish), case-insensitive
- ⏰ **Scheduled scans** — twice a day via cron (configurable times)
- ⚡ **On-demand scan** — trigger manually with `/scan` at any time
- 🔁 **Duplicate prevention** — already-seen messages are skipped
- 🔘 **Inline action buttons** — each forwarded message includes:
  - 🔎 *Open message in group*
  - ✉ *Write to the author*
- 🛠 **Full bot management** — manage groups and keywords via Telegram commands

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Telegram (userbot) | [Telethon](https://github.com/LonamiWebs/Telethon) |
| Telegram (bot) | Telethon Bot API |
| Database | SQLite via `aiosqlite` |
| Scheduler | APScheduler (AsyncIO) |
| Packaging | `uv` + `hatchling` |
| Deployment | Docker / Docker Compose |

---

## 🤖 Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/help` | Status: groups, keywords, last scan |
| `/add_group <link>` | Add a group to monitoring |
| `/remove_group <link>` | Remove a group |
| `/list_groups` | Show all monitored groups |
| `/add_keyword <word>` | Add a keyword |
| `/remove_keyword <word>` | Remove a keyword |
| `/list_keywords` | Show all keywords |
| `/scan` | Run a scan immediately |

---

## 🚀 Quick Start

```bash
cp .env.example .env   # fill in your credentials
uv sync
uv run python -m izimir   # first run will ask for your phone number
```

---

## 🐳 Deploy with Docker

```bash
cp .env.example .env
mkdir data
docker compose run --rm bot   # first run — Telegram authorization
docker compose up -d          # run 24/7
```

---

## ⚙️ Configuration

Create a `.env` file based on `.env.example`:

| Variable | Description |
|---|---|
| `API_ID` | Telegram API ID from [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | Telegram API Hash |
| `BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `OWNER_ID` | Your numeric Telegram user ID |
| `SCAN_TIMES` | Scan schedule, e.g. `09:00,18:00` (default) |
| `TIMEZONE` | Timezone, e.g. `Europe/Istanbul` (default) |
| `MESSAGES_LIMIT` | Max messages per group per scan (default: `500`) |
| `RATE_LIMIT_DELAY` | Delay between groups in seconds (default: `2.0`) |

---

## 🏗 Project Structure

```
src/izimir/
├── __main__.py      # Entry point, startup & shutdown
├── bot_handlers.py  # All bot command handlers
├── scanner.py       # Core scan logic with lock (no concurrent scans)
├── scheduler.py     # APScheduler setup (cron-based)
├── formatter.py     # Message formatting & inline buttons
├── clients.py       # Telethon client factories
├── db.py            # SQLite database layer
└── config.py        # Settings loaded from .env
```

---

## 📋 How It Works

1. The **userbot** joins the monitored groups using the owner's Telegram account
2. Every scan loads messages from the last 24 hours for each active group
3. Messages are checked against the keyword list
4. Matched messages that haven't been seen before are forwarded to the owner
5. Each forwarded message includes inline buttons to open the original or contact the author
6. A **concurrent scan lock** prevents overlap between scheduled and manual scans

---

## 📄 License

MIT
