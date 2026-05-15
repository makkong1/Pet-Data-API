"""Phase 2: POST /events/recommendation — 인증·검증·202 응답."""

import hashlib
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("app.platform.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.platform.core.config.settings.ADMIN_API_KEY_HASH", "different_hash")


@pytest.fixture
def mock_db(monkeypatch):
    @asynccontextmanager
    async def mock_session():
        mock = AsyncMock()
        yield mock

    monkeypatch.setattr("app.platform.core.database.AsyncSessionLocal", mock_session)


@pytest.mark.asyncio
async def test_events_requires_api_key(mock_settings, mock_db):
    from app.main import app
    payload = {
        "request_id": "abc123",
        "events": [
            {"facility_id": 1, "event": "view", "occurred_at": "2026-05-13T12:00:00Z"}
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/events/recommendation", json=payload)
    assert response.status_code == 422  # missing X-API-Key


@pytest.mark.asyncio
async def test_events_accepts_valid_payload(mock_settings, mock_db):
    from app.main import app
    payload = {
        "request_id": "abc123",
        "events": [
            {"facility_id": 1, "event": "view", "occurred_at": "2026-05-13T12:00:00Z"},
            {"facility_id": 2, "event": "click", "occurred_at": "2026-05-13T12:01:00Z"},
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/events/recommendation", json=payload, headers=HEADERS)

    assert response.status_code == 202
    data = response.json()
    assert data["accepted"] == 2
    assert data["skipped"] == 0


@pytest.mark.asyncio
async def test_events_skips_when_no_identifier(mock_settings, mock_db):
    from app.main import app
    payload = {
        "events": [
            {"event": "view", "occurred_at": "2026-05-13T12:00:00Z"},
            {"source_id": "B001", "event": "click", "occurred_at": "2026-05-13T12:01:00Z"},
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/events/recommendation", json=payload, headers=HEADERS)

    assert response.status_code == 202
    data = response.json()
    assert data["accepted"] == 1
    assert data["skipped"] == 1


@pytest.mark.asyncio
async def test_events_validates_event_type(mock_settings, mock_db):
    from app.main import app
    payload = {
        "events": [
            {"facility_id": 1, "event": "bogus", "occurred_at": "2026-05-13T12:00:00Z"},
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/events/recommendation", json=payload, headers=HEADERS)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_events_empty_array_rejected(mock_settings, mock_db):
    from app.main import app
    payload = {"events": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/events/recommendation", json=payload, headers=HEADERS)
    assert response.status_code == 422
