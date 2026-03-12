from __future__ import annotations

from telethon.tl.types import Message, Channel, User
from telethon.tl.custom import Button


def _author_info(sender: User | Channel | None) -> tuple[str, str | None, int | None]:
    """Return (display_name, username_or_none, user_id_or_none)."""
    if sender is None:
        return "Unknown", None, None
    if isinstance(sender, User):
        name = " ".join(filter(None, [sender.first_name, sender.last_name]))
        return name or "No name", sender.username, sender.id
    if isinstance(sender, Channel):
        return sender.title or "Channel", sender.username, None
    return "Unknown", None, None


def format_found_message(
    msg: Message,
    group_title: str,
    group_username: str | None,
    group_id: int,
    group_link: str,
) -> tuple[str, list[list[Button]]]:
    sender = msg.sender
    author_name, author_username, author_id = _author_info(sender)

    author_line = f"@{author_username}" if author_username else author_name
    date_str = msg.date.strftime("%d.%m.%Y %H:%M") if msg.date else "?"

    text = msg.text or ""
    if len(text) > 1000:
        text = text[:1000] + "…"

    body = (
        f"📢 **Potential listing found**\n"
        f"👤 Author: {author_line}\n"
        f"👥 Group: {group_title}\n"
        f"🕒 Date: {date_str}\n"
        f"💬 Message:\n{text}"
    )

    buttons: list[list[Button]] = []

    # Message deep link
    if group_username:
        msg_link = f"https://t.me/{group_username}/{msg.id}"
    else:
        real_id = group_id if group_id > 0 else -group_id - 1000000000000
        msg_link = f"https://t.me/c/{real_id}/{msg.id}"

    buttons.append([Button.url("🔎 Open message", msg_link)])

    # Join group button
    if group_username:
        buttons.append([Button.url("👥 Open group", f"https://t.me/{group_username}")])
    elif group_link:
        buttons.append([Button.url("👥 Open group", group_link)])

    # Contact author button
    if author_username:
        buttons.append([Button.url("✉ Write to author", f"https://t.me/{author_username}")])
    elif author_id:
        buttons.append([Button.url("✉ Write to author", f"tg://user?id={author_id}")])

    return body, buttons
