"""Izimir Mini App backend (FastAPI).

Serves the WebApp UI and an owner-only JSON API over the same SQLite DB the bot
uses (WAL enables concurrent access). Actions needing the user account
(add/remove group, scan) are pushed to ``command_queue`` and run by the bot.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from izimir.config import load_settings
from izimir.db import Database
from izimir.texts import detect_language
from izimir.webapp.auth import owner_from_init_data

settings = load_settings()
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database(settings.db_path)
    await db.connect()
    app.state.db = db
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="Izimir Mini App", lifespan=lifespan)


def get_db(request: Request) -> Database:
    return request.app.state.db


async def require_owner(authorization: str = Header(default="")) -> dict:
    raw = authorization[4:] if authorization.startswith("tma ") else authorization
    user = owner_from_init_data(raw, settings.bot_token, settings.owner_id)
    if user is None:
        raise HTTPException(status_code=403, detail="forbidden")
    return user


# --- read API (direct DB) ------------------------------------------------


@app.get("/api/leads")
async def api_leads(
    group: str = "",
    q: str = "",
    limit: int = 200,
    _: dict = Depends(require_owner),
    db: Database = Depends(get_db),
):
    finds = await db.recent_finds(limit=2000)
    g, query = group.casefold(), q.casefold()
    out = []
    for f in finds:
        if g and g not in (f["group_title"] or "").casefold():
            continue
        if query and query not in (f["text"] or "").casefold():
            continue
        out.append(f)
        if len(out) >= limit:
            break
    return {"leads": out}


@app.get("/api/stats")
async def api_stats(_: dict = Depends(require_owner), db: Database = Depends(get_db)):
    return await db.find_stats()


@app.get("/api/keywords")
async def api_keywords(
    _: dict = Depends(require_owner), db: Database = Depends(get_db)
):
    return {"keywords": await db.list_keywords()}


@app.get("/api/groups")
async def api_groups(_: dict = Depends(require_owner), db: Database = Depends(get_db)):
    return {"groups": await db.list_groups()}


# --- write API (keywords direct; groups/scan via queue) ------------------


@app.post("/api/keywords")
async def api_add_keyword(
    request: Request,
    _: dict = Depends(require_owner),
    db: Database = Depends(get_db),
):
    body = await request.json()
    kw = (body.get("keyword") or "").strip()
    if not kw:
        raise HTTPException(status_code=400, detail="empty keyword")
    added = await db.add_keyword(kw, detect_language(kw))
    return {"added": added, "keyword": kw}


@app.delete("/api/keywords")
async def api_del_keyword(
    request: Request,
    _: dict = Depends(require_owner),
    db: Database = Depends(get_db),
):
    body = await request.json()
    kw = (body.get("keyword") or "").strip()
    removed = await db.remove_keyword(kw)
    return {"removed": removed}


@app.post("/api/groups")
async def api_add_group(
    request: Request,
    _: dict = Depends(require_owner),
    db: Database = Depends(get_db),
):
    body = await request.json()
    link = (body.get("link") or "").strip()
    if not link:
        raise HTTPException(status_code=400, detail="empty link")
    return {"command_id": await db.enqueue_command("add_group", {"link": link})}


@app.delete("/api/groups")
async def api_del_group(
    request: Request,
    _: dict = Depends(require_owner),
    db: Database = Depends(get_db),
):
    body = await request.json()
    link = (body.get("link") or "").strip()
    return {"command_id": await db.enqueue_command("remove_group", {"link": link})}


@app.post("/api/scan")
async def api_scan(
    request: Request,
    _: dict = Depends(require_owner),
    db: Database = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        body = {}
    days = body.get("days")
    payload = {"days": days} if days else {}
    return {"command_id": await db.enqueue_command("scan", payload)}


@app.get("/api/command/{command_id}")
async def api_command(
    command_id: int,
    _: dict = Depends(require_owner),
    db: Database = Depends(get_db),
):
    cmd = await db.get_command(command_id)
    if cmd is None:
        raise HTTPException(status_code=404, detail="not found")
    return cmd


# --- static UI -----------------------------------------------------------


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
