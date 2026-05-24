import hashlib

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app

ADMIN_KEY = "adminkey"
ADMIN_KEY_HASH = hashlib.sha256(ADMIN_KEY.encode()).hexdigest()


@pytest.fixture(autouse=True)
def patch_keys(monkeypatch):
    monkeypatch.setattr(
        "app.platform.core.config.settings.API_KEY_HASH",
        hashlib.sha256(b"user_only").hexdigest(),
    )
    monkeypatch.setattr("app.platform.core.config.settings.ADMIN_API_KEY_HASH", ADMIN_KEY_HASH)


def _admin_headers():
    return {"X-API-Key": ADMIN_KEY}


@pytest.mark.asyncio
async def test_trigger_collection_popular_only():
    with patch("app.serving.api.collect.run_popular_collection", new=AsyncMock()) as mock_popular, \
         patch("app.serving.api.collect.run_trend_collection", new=AsyncMock()) as mock_trends:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/collect/trigger",
                json={"targets": ["popular"]},
                headers=_admin_headers(),
            )
    assert resp.status_code == 202
    data = resp.json()
    assert data["targets"] == ["popular"]
    assert data.get("request_id")
    mock_popular.assert_called_once()
    mock_trends.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_collection_trends_only():
    with patch("app.serving.api.collect.run_trend_collection", new=AsyncMock()) as mock_trends, \
         patch("app.serving.api.collect.run_popular_collection", new=AsyncMock()) as mock_popular:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/collect/trigger",
                json={"targets": ["trends"]},
                headers=_admin_headers(),
            )
    assert resp.status_code == 202
    data = resp.json()
    assert data["targets"] == ["trends"]
    assert data.get("request_id")
    mock_trends.assert_called_once()
    mock_popular.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_collection_both():
    with patch("app.serving.api.collect.run_popular_collection", new=AsyncMock()) as mock_popular, \
         patch("app.serving.api.collect.run_trend_collection", new=AsyncMock()) as mock_trends:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/collect/trigger",
                json={"targets": ["popular", "trends"]},
                headers=_admin_headers(),
            )
    assert resp.status_code == 202
    data = resp.json()
    assert set(data["targets"]) == {"popular", "trends"}
    assert data.get("request_id")
    mock_popular.assert_called_once()
    mock_trends.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_collection_dedup_targets():
    with patch("app.serving.api.collect.run_popular_collection", new=AsyncMock()), \
         patch("app.serving.api.collect.run_trend_collection", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/collect/trigger",
                json={"targets": ["popular", "popular", "trends"]},
                headers=_admin_headers(),
            )
    assert resp.status_code == 202
    data = resp.json()
    assert data["targets"] == ["popular", "trends"]
    assert data.get("request_id")


@pytest.mark.asyncio
async def test_trigger_collection_invalid_target_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/collect/trigger",
            json={"targets": ["invalid_target"]},
            headers=_admin_headers(),
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trigger_collection_requires_admin_missing_header():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/collect/trigger", json={"targets": ["trends"]})
    assert resp.status_code == 401
    assert resp.json().get("detail") == "Missing X-API-Key header"


@pytest.mark.asyncio
async def test_trigger_collection_user_key_forbidden():
    user_key = "user_only"
    user_headers = {"X-API-Key": user_key}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/collect/trigger",
            json={"targets": ["trends"]},
            headers=user_headers,
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trigger_collection_wait_inline_200():
    with patch(
        "app.serving.api.collect.run_popular_collection",
        new=AsyncMock(return_value=[{"context": "grooming", "status": "success"}]),
    ) as mp, patch(
        "app.serving.api.collect.run_trend_collection",
        new=AsyncMock(),
    ) as mt:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/collect/trigger",
                json={"targets": ["popular"]},
                headers=_admin_headers(),
                params={"wait": True},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "collection finished"
    assert body["results"]["popular"]["status"] == "ok"
    assert body["results"]["popular"]["detail"] == [
        {"context": "grooming", "status": "success"},
    ]
    mp.assert_awaited_once()
    mt.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_digest_looking_plaintext_explainer_401():
    bogus_hex_key = "0" * 64
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/collect/trigger",
            json={"targets": ["trends"]},
            headers={"X-API-Key": bogus_hex_key},
        )
    assert resp.status_code == 401
    detail = resp.json().get("detail") or ""
    assert "plaintext" in detail.lower()
