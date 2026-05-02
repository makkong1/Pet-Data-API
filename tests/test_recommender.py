import pytest
from unittest.mock import AsyncMock, MagicMock
from app.recommender.facilities import get_nearby_facilities, VALID_CONTEXTS


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
    mock_row = {"name": "해피독", "distance_m": 320.5, "address": "서울시 마포구", "lat": 37.56, "lng": 126.97}
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


from app.recommender.builder import build_prompt


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


def test_build_prompt_no_pet():
    prompt = build_prompt("hospital", [], [], None)
    assert "반려동물" not in prompt
    assert "동물병원" in prompt
