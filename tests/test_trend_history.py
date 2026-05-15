"""Phase 1: trend_history.persist_trend_snapshot 단위 테스트 (DB 호출 자체는 mock)."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.trend_history import persist_trend_snapshot


@pytest.mark.asyncio
async def test_persist_trend_snapshot_skips_empty_counts():
    rows = await persist_trend_snapshot("snack", {})
    assert rows == 0


@pytest.mark.asyncio
async def test_persist_trend_snapshot_inserts_each_keyword():
    """upsert SQL 이 한 번 실행되고, executemany style 로 모든 키워드를 한 번에 적재."""
    captured: dict = {}

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt, params):
            captured["params"] = params

        async def commit(self):
            captured["committed"] = True

    with patch("app.ingestion.trend_history.AsyncSessionLocal", return_value=_FakeSession()):
        rows = await persist_trend_snapshot(
            "snack",
            {"오리젠": 10, "로얄캐닌": 7},
            snapshot_date=date(2026, 5, 13),
        )

    assert rows == 2
    assert captured["committed"] is True
    keywords = {row["keyword"] for row in captured["params"]}
    assert keywords == {"오리젠", "로얄캐닌"}
    for row in captured["params"]:
        assert row["snapshot_date"] == date(2026, 5, 13)
        assert row["category"] == "snack"
