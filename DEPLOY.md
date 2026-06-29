# Deploying Izimir on a VPS (Docker)

Production deployment runs three containers via Docker Compose: **bot** (Telethon
user + bot clients, scheduler, queue worker), **web** (the Mini App / FastAPI),
and **caddy** (automatic HTTPS via Let's Encrypt). The Mini App is optional — skip
the domain steps and it simply won't be served.

## Prerequisites

- A Linux VPS (Ubuntu 22.04+ / Debian 12+), ~512 MB RAM is enough.
- Docker + Docker Compose (installed below).
- Telegram `API_ID` / `API_HASH` (https://my.telegram.org), a bot token from
  [@BotFather](https://t.me/BotFather), and your numeric Telegram user id.
- For the Mini App: a free HTTPS domain. A **DuckDNS** subdomain works well.

## 0. DNS (Mini App only, once)

Create a free subdomain at [duckdns.org](https://www.duckdns.org) and point its
**A record to your VPS IP** (e.g. `your-name.duckdns.org → 203.0.113.10`).

> The DuckDNS token is a **secret** — keep it out of the repo. It is only used to
> update the A record (via the DuckDNS web UI or their update URL on the VPS).

## 1. Server setup

```bash
ssh root@<VPS_IP>
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh
# open ports for SSH and Caddy's automatic HTTPS:
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable
```

If your cloud provider has its own firewall / security group, open 80 and 443 there too.

## 2. Get the code and configure

```bash
git clone https://github.com/humeniuk-dmytro/izimir.git && cd izimir
cp .env.example .env
nano .env
mkdir -p data
```

Fill in `.env`:

```ini
API_ID=...
API_HASH=...
BOT_TOKEN=...
OWNER_ID=...                       # numeric id; only this user can use the bot
# Mini App (optional):
WEBAPP_DOMAIN=your-name.duckdns.org
WEBAPP_URL=https://your-name.duckdns.org
```

Schedule and search window can be tuned (`SCAN_TIMES`, `SCAN_HOURS`, `TIMEZONE`);
defaults are 09:00 & 18:00 Europe/Istanbul, 24h window.

## 3. First run — log in the user account (interactive)

The user account is authenticated once via phone number + code:

```bash
docker compose run --rm bot
# enter phone number → enter the code from Telegram → wait for "Bot is running" → Ctrl+C
```

Session files are saved under `data/` and survive restarts.

## 4. Run 24/7

```bash
docker compose up -d        # starts bot + web + caddy, auto-restart
docker compose logs -f      # follow logs (Ctrl+C to stop following)
```

On first start Caddy obtains a Let's Encrypt certificate for `WEBAPP_DOMAIN`, and
the bot sets its menu button to `WEBAPP_URL`.

## 5. Verify

- Send `/help` to the bot — it replies with status and the command list.
- Tap the **📊 Панель** menu button — the Mini App opens at your domain.
- Send `/scan` — a manual scan runs and reports back.
- At each `SCAN_TIMES` moment the bot posts a **scheduled scan** summary to the
  owner chat, even when nothing is found (so you can see the schedule working).

## Operations

```bash
docker compose ps               # status
docker compose logs --tail 100  # recent logs
docker compose restart          # restart
docker compose down             # stop
# update to the latest code:
git pull && docker compose up -d --build
```

> The schedule only fires while the container is running, so keep it `up -d`
> (auto-restart handles reboots/crashes). Scan times follow `TIMEZONE`.

## Without Docker (systemd alternative)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv
cd ~/izimir && cp .env.example .env && nano .env && uv sync
uv run python -m izimir          # first run: phone + code, then Ctrl+C
```

Then a unit at `/etc/systemd/system/izimir.service` with
`ExecStart=/root/.local/bin/uv run python -m izimir` and `Restart=always`,
enabled with `systemctl enable --now izimir`. (Docker is recommended — it also
runs the Mini App and HTTPS for you.)
