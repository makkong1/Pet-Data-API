import pytest
from unittest.mock import AsyncMock, MagicMock
from app.serving.recommender.facilities import get_nearby_facilities, VALID_CONTEXTS


@pytest.mark.asyncio
async def test_get_nearby_facilities_unknown_context_returns_empty():
    """알 수 없는 context는 빈 배열."""
    db = AsyncMock()
    result = await get_nearby_facilities(db, 37.5, 126.9, "unknown", 3.0, 5)
    assert result == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_nearby_facilities_grooming_returns_rows():
    """grooming context → BUSINESS 타입 시설 반환."""
    mock_row = {"source_id": "B001", "name": "해피독", "distance_m": 320.5, "address": "서울시 마포구", "lat": 37.56, "lng": 126.97}
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    result = await get_nearby_facilities(db, 37.5665, 126.978, "grooming", 3.0, 5)

    assert len(result) == 1
    assert result[0]["name"] == "해피독"
    assert result[0]["distance_m"] == 320
    db.execute.assert_called_once()


def test_valid_contexts():
    assert "grooming" in VALID_CONTEXTS
    assert "hospital" in VALID_CONTEXTS
    assert "snack" in VALID_CONTEXTS
    assert "supplies" in VALID_CONTEXTS


from app.serving.recommender.builder import build_prompt, build_trend_only_copy


def test_build_prompt_with_pet_and_facilities():
    facilities = [{"name": "해피독", "distance_m": 320, "address": "서울"}]
    trends = [{"keyword": "스포팅컷", "score": 41}]
    pet = {"type": "dog", "breed": "말티즈", "age": "2살"}

    prompt = build_prompt("grooming", facilities, trends, pet)

    assert "말티즈" in prompt
    assert "미용실" in prompt
    assert "해피독(320m)" in prompt
    assert "스포팅컷" in prompt


def test_build_prompt_no_facilities():
    prompt = build_prompt("snack", [], [{"keyword": "오리젠", "score": 10}], None)
    assert "주변 시설 정보 없음" in prompt
    assert "오리젠" in prompt


def test_build_trend_only_copy_uses_keywords_only():
    text = build_trend_only_copy("grooming", [("미용", 100), ("미용실", 50)])
    assert "미용" in text
    assert "공공데이터" in text or "반경" in text
    assert "Pawsome" not in text
