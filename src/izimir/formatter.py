from __future__ import annotations

from telethon.tl.types import Message, Channel, User
from telethon.tl.custom import Button

from izimir import texts


def _author_info(sender: User | Channel | None) -> tuple[str, str | None, int | None]:
    """Return (display_name, username_or_none, user_id_or_none)."""
    if sender is None:
        return texts.AUTHOR_UNKNOWN, None, None
    if isinstance(sender, User):
        name = " ".join(filter(None, [sender.first_name, sender.last_name]))
        return name or texts.AUTHOR_NO_NAME, sender.username, sender.id
    if isinstance(sender, Channel):
        return sender.title or texts.AUTHOR_UNKNOWN, sender.username, None
    return texts.AUTHOR_UNKNOWN, None, None


def message_link(group_username: str | None, group_id: int, msg_id: int) -> str:
    """Deep link to a specific message (public username or private t.me/c)."""
    if group_username:
        return f"https://t.me/{group_username}/{msg_id}"
    real_id = group_id if group_id > 0 else -group_id - 1000000000000
    return f"https://t.me/c/{real_id}/{msg_id}"


def lead_fields(
    msg: Message, group_title: str, group_username: str | None, group_id: int
) -> dict:
    """Structured lead data for persistence in the finds table."""
    name, username, _ = _author_info(msg.sender)
    return {
        "message_id": msg.id,
        "group_id": group_id,
        "group_title": group_title,
        "author": name,
        "author_username": username,
        "text": (msg.text or "")[:2000],
        "msg_link": message_link(group_username, group_id, msg.id),
    }


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

    body = "\n".join(
        [
            texts.FOUND_HEADER,
            texts.FOUND_AUTHOR.format(author=author_line),
            texts.FOUND_GROUP.format(group=group_title),
            texts.FOUND_DATE.format(date=date_str),
            texts.FOUND_MESSAGE.format(text=text),
        ]
    )

    buttons: list[list[Button]] = []

    # Message deep link
    msg_link = message_link(group_username, group_id, msg.id)
    buttons.append([Button.url(texts.BTN_OPEN_MESSAGE, msg_link)])

    # Join group button
    if group_username:
        buttons.append(
            [Button.url(texts.BTN_OPEN_GROUP, f"https://t.me/{group_username}")]
        )
    elif group_link:
        buttons.append([Button.url(texts.BTN_OPEN_GROUP, group_link)])

    # Contact author button
    if author_username:
        buttons.append(
            [Button.url(texts.BTN_WRITE_AUTHOR, f"https://t.me/{author_username}")]
        )
    elif author_id:
        buttons.append(
            [Button.url(texts.BTN_WRITE_AUTHOR, f"tg://user?id={author_id}")]
        )

    return body, buttons
