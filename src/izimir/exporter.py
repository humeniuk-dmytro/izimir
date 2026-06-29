"""CSV export of leads, shared by the /export command and the Mini App queue."""

from __future__ import annotations

import csv
import io

CSV_HEADER = ["found_at", "group", "author", "username", "text", "link"]
CSV_FILENAME = "izimir_leads.csv"


def leads_csv(finds: list[dict]) -> io.BytesIO:
    """Build a downloadable CSV (UTF-8 with BOM, oldest-first) from finds.

    The BOM makes Excel open Cyrillic correctly. ``finds`` is the newest-first
    list from ``db.recent_finds``; rows are reversed to chronological order.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    for f in reversed(finds):
        writer.writerow(
            [
                f["found_at"],
                f["group_title"],
                f["author"] or "",
                f["author_username"] or "",
                f["text"],
                f["msg_link"] or "",
            ]
        )
    bio = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    bio.name = CSV_FILENAME
    return bio
