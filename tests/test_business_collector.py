import pytest
from unittest.mock import AsyncMock, patch

from app.collector.business import parse_business_item, extract_businesses, fetch_all_businesses


def test_parse_business_item_maps_fields():
    raw = {
        "MNG_NO": "370000004920180033",
        "BPLC_NM": "행복 펫 미용",
        "SALS_STTS_NM": "영업/정상",
        "ROAD_NM_ADDR": "서울특별시 강남구 테헤란로 123",
        "TELNO": "02-1234-5678",
    }
    result = parse_business_item(raw)
    assert result["name"] == "행복 펫 미용"
    assert result["status"] == "영업"
    assert result["region_city"] == "서울특별시"
    assert result["region_district"] == "강남구"
    assert result["type"] == "BUSINESS"
    assert result["business_type"] == "동물미용업"
    assert result["source_id"] == "370000004920180033"


def test_parse_business_item_missing_phone():
    raw = {
        "MNG_NO": "BIZ-002",
        "BPLC_NM": "테스트",
        "SALS_STTS_NM": "영업/정상",
        "ROAD_NM_ADDR": "서울특별시 강남구 어딘가 123",
        "TELNO": "",
    }
    result = parse_business_item(raw)
    assert result["phone"] is None
    assert result["source_id"] == "BIZ-002"
    assert result["status"] == "영업"


def test_extract_businesses_raises_on_api_error():
    bad_response = {
        "response": {
            "header": {
                "resultCode": "30",
                "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
            },
            "body": {},
        }
    }

    with pytest.raises(RuntimeError):
        extract_businesses(bad_response)


@pytest.mark.asyncio
async def test_fetch_all_businesses_collects_multiple_pages():
    page1 = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {
                "totalCount": 3,
                "items": {
                    "item": [
                        {"MNG_NO": "B1", "BPLC_NM": "A", "SALS_STTS_NM": "영업/정상", "ROAD_NM_ADDR": "서울 강남구 1"},
                        {"MNG_NO": "B2", "BPLC_NM": "B", "SALS_STTS_NM": "영업/정상", "ROAD_NM_ADDR": "서울 강남구 2"},
                    ]
                },
            },
        }
    }
    page2 = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {
                "totalCount": 3,
                "items": {
                    "item": {"MNG_NO": "B3", "BPLC_NM": "C", "SALS_STTS_NM": "폐업", "ROAD_NM_ADDR": "서울 강남구 3"}
                },
            },
        }
    }

    with patch("app.collector.business.fetch_businesses", new=AsyncMock(side_effect=[page1, page2])) as mocked:
        rows = await fetch_all_businesses(num_of_rows=2)

    assert len(rows) == 3
    assert rows[0]["status"] == "영업"
    assert rows[-1]["status"] == "폐업"
    assert mocked.await_count == 2
