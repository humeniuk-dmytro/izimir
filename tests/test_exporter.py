"""Tests for the shared CSV export helper."""

from __future__ import annotations

from izimir.exporter import CSV_HEADER, leads_csv


def _find(found_at, text, username=None, link=None):
    return {
        "found_at": found_at,
        "group_title": "Группа",
        "author": "Автор",
        "author_username": username,
        "text": text,
        "msg_link": link,
    }


def test_leads_csv_has_bom_header_and_data():
    bio = leads_csv([_find("2026-06-01", "сдается квартира", "ivan", "l")])
    raw = bio.getvalue()
    assert raw[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM for Excel
    text = raw.decode("utf-8-sig")
    assert ",".join(CSV_HEADER) in text
    assert "сдается квартира" in text
    assert bio.name == "izimir_leads.csv"


def test_leads_csv_reverses_to_chronological_order():
    # recent_finds is newest-first; the CSV must be oldest-first
    finds = [_find("2", "second"), _find("1", "first")]
    text = leads_csv(finds).getvalue().decode("utf-8-sig")
    assert text.index("first") < text.index("second")


def test_leads_csv_handles_missing_fields():
    text = (
        leads_csv([_find("1", "квартира", None, None)]).getvalue().decode("utf-8-sig")
    )
    assert "квартира" in text  # None username/link become empty cells, no crash
