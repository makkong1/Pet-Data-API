import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.ingestion.geocoder import geocode_address


@pytest.mark.asyncio
async def test_geocode_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "documents": [{"y": "37.5665", "x": "126.9780"}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.ingestion.geocoder.settings") as mock_settings, \
         patch("app.ingestion.geocoder.httpx.AsyncClient") as mock_client_cls:
        mock_settings.KAKAO_REST_API_KEY = "kakao-test-key"
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        result = await geocode_address("서울시 마포구 어딘가")

    assert result == (37.5665, 126.9780)


@pytest.mark.asyncio
async def test_geocode_no_key_returns_none():
    with patch("app.ingestion.geocoder.settings") as mock_settings:
        mock_settings.KAKAO_REST_API_KEY = ""
        result = await geocode_address("서울시 어딘가")
    assert result is None


@pytest.mark.asyncio
async def test_geocode_empty_docs_returns_none():
    mock_response = MagicMock()
    mock_response.json.return_value = {"documents": []}
    mock_response.raise_for_status = MagicMock()

    with patch("app.ingestion.geocoder.settings") as mock_settings, \
         patch("app.ingestion.geocoder.httpx.AsyncClient") as mock_client_cls:
        mock_settings.KAKAO_REST_API_KEY = "kakao-test-key"
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        result = await geocode_address("존재하지않는주소")
    assert result is None
