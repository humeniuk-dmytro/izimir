from __future__ import annotations

import pytest_asyncio

from izimir.db import Database


@pytest_asyncio.fixture
async def db():
    """Fresh in-memory database for each test."""
    database = Database(":memory:")
    await database.connect()
    try:
        yield database
    finally:
        await database.close()
