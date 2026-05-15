"""Phase 0: observability — request_id 미들웨어, /healthz, /readyz, /metrics."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_healthz_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_request_id_generated_when_missing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/healthz")
    assert response.headers.get("x-request-id"), "X-Request-Id should be set by middleware"
    assert len(response.headers["x-request-id"]) >= 8


@pytest.mark.asyncio
async def test_request_id_echoed_when_provided():
    incoming = "petory-trace-abc123"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/healthz", headers={"X-Request-Id": incoming})
    assert response.headers.get("x-request-id") == incoming


@pytest.mark.asyncio
async def test_metrics_endpoint_exposed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "python_info" in body or "process_" in body or "http_request" in body


@pytest.mark.asyncio
async def test_readyz_degraded_when_db_or_redis_down():
    """DB·Redis 둘 다 실패하는 상황에서 503 degraded 반환."""

    class _FailingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *args, **kwargs):
            raise RuntimeError("db unavailable")

    fake_redis = MagicMock()
    fake_redis.ping = AsyncMock(side_effect=RuntimeError("redis down"))

    with patch("app.platform.observability.AsyncSessionLocal", return_value=_FailingSession()), \
         patch("app.platform.observability.get_redis", return_value=fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["db"].startswith("error")
    assert body["checks"]["redis"].startswith("error")
