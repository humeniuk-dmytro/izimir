"""Тести шару БД: групи, ключові слова, дедуп, scan_log, лічильники."""

from __future__ import annotations


# --- ключові слова -------------------------------------------------------


async def test_add_list_keywords(db):
    assert await db.add_keyword("квартира", "ru")
    assert await db.add_keyword("kiralık", "tr")
    assert await db.list_keywords() == ["kiralık", "квартира"]  # ORDER BY keyword
    assert await db.keyword_count() == 2


async def test_keyword_duplicate_case_insensitive(db):
    assert await db.add_keyword("Снять")
    # NOCASE: повторне додавання іншим регістром відхиляється
    assert not await db.add_keyword("снять")
    assert await db.keyword_count() == 1


async def test_remove_keyword_case_insensitive(db):
    await db.add_keyword("Квартира")
    assert await db.remove_keyword("КВАРТИРА")
    assert await db.keyword_count() == 0
    assert not await db.remove_keyword("неіснуюче")


# --- групи ---------------------------------------------------------------


async def test_add_group_with_access_hash(db):
    assert await db.add_group(123, "https://t.me/test", "Test Group", 999)
    groups = await db.get_active_groups()
    assert len(groups) == 1
    assert groups[0]["group_id"] == 123
    assert groups[0]["access_hash"] == 999


async def test_add_duplicate_group(db):
    await db.add_group(1, "link", "A")
    assert not await db.add_group(1, "link2", "B")


async def test_deactivate_group_excluded_from_active(db):
    await db.add_group(1, "link", "A")
    await db.deactivate_group(1)
    assert await db.get_active_groups() == []
    assert await db.group_count() == 0
    # але лишається в повному списку
    assert len(await db.list_groups()) == 1


async def test_remove_group_by_id_and_link(db):
    await db.add_group(1, "https://t.me/a", "A")
    await db.add_group(2, "https://t.me/b", "B")
    assert await db.remove_group(1)
    assert await db.remove_group_by_link("https://t.me/b")
    assert await db.group_count() == 0


# --- дедуплікація --------------------------------------------------------


async def test_processed_messages_dedup(db):
    assert not await db.is_processed(10, 1)
    await db.mark_processed(10, 1)
    assert await db.is_processed(10, 1)
    # повторна позначка не падає (INSERT OR IGNORE)
    await db.mark_processed(10, 1)
    # той самий msg_id в іншій групі — окремо
    assert not await db.is_processed(10, 2)


async def test_cleanup_processed_messages(db):
    await db.mark_processed(1, 1)
    # свіжі не видаляються
    assert await db.cleanup_processed_messages(keep_days=7) == 0
    assert await db.is_processed(1, 1)


# --- scan_log та лічильники ---------------------------------------------


async def test_scan_log_lifecycle(db):
    sid = await db.start_scan("2026-06-25T09:00:00")
    last = await db.last_scan()
    assert last["status"] == "running"

    await db.finish_scan(sid, "2026-06-25T09:01:00", 1, 3, "ok")
    last = await db.last_scan()
    assert last["status"] == "ok"
    assert last["messages_found"] == 3


async def test_total_found_counts_leads(db):
    # total_found уніфіковано з finds/stats (ТЗ 5.3)
    assert await db.total_found() == 0
    await _add_find(db, 1)
    await _add_find(db, 2)
    assert await db.total_found() == 2


# --- finds (ліди) --------------------------------------------------------


async def _add_find(
    db, mid, gid=1, title="G", author="A", username="a", text="квартира"
):
    await db.add_find(
        mid, gid, title, author, username, text, f"https://t.me/c/{gid}/{mid}"
    )


async def test_add_and_recent_finds(db):
    await _add_find(db, 1, text="сдается квартира")
    await _add_find(db, 2, text="kiralık daire")
    finds = await db.recent_finds()
    assert len(finds) == 2
    assert finds[0]["message_id"] == 2  # ORDER BY id DESC
    assert finds[0]["msg_link"] == "https://t.me/c/1/2"


async def test_add_find_idempotent(db):
    await _add_find(db, 1)
    await _add_find(db, 1)  # той самий (message_id, group_id) — не дублюється
    assert len(await db.recent_finds()) == 1


async def test_find_stats(db):
    await _add_find(db, 1, gid=1, title="Недвижимость")
    await _add_find(db, 2, gid=1, title="Недвижимость")
    await _add_find(db, 3, gid=2, title="Барахолка")
    stats = await db.find_stats()
    assert stats["total"] == 3
    assert stats["today"] == 3
    assert stats["week"] == 3
    assert stats["by_group"][0] == ("Недвижимость", 2)  # топ-група


async def test_find_stats_empty(db):
    stats = await db.find_stats()
    assert stats == {"total": 0, "today": 0, "week": 0, "by_group": []}


async def test_clear_processed(db):
    await db.mark_processed(1, 1)
    await db.mark_processed(2, 1)
    assert await db.clear_processed() == 2
    assert not await db.is_processed(1, 1)


# --- command queue (Mini App bridge) -------------------------------------


async def test_command_queue_lifecycle(db):
    cid = await db.enqueue_command("scan", {"days": 7})
    assert cid > 0
    cmd = await db.claim_pending_command()
    assert cmd["id"] == cid
    assert cmd["type"] == "scan"
    assert cmd["payload"] == {"days": 7}
    # claimed → більше не pending
    assert await db.claim_pending_command() is None
    await db.finish_command(cid, "done", "ок")
    got = await db.get_command(cid)
    assert got["status"] == "done"
    assert got["result"] == "ок"


async def test_command_queue_is_fifo(db):
    a = await db.enqueue_command("scan", {})
    b = await db.enqueue_command("add_group", {"link": "x"})
    assert (await db.claim_pending_command())["id"] == a
    assert (await db.claim_pending_command())["id"] == b
