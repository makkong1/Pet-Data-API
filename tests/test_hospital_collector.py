import pytest
from unittest.mock import AsyncMock, patch

from app.collector.hospital import parse_hospital_item, extract_hospitals, fetch_all_hospitals


def test_parse_hospital_item_maps_fields():
    raw = {
        "MNG_NO": "HOSP-001",
        "BPLC_NM": "강남동물병원",
        "SALS_STTS_NM": "영업/정상",
        "ROAD_NM_ADDR": "서울특별시 강남구 봉은사로 123",
        "TELNO": "02-9876-5432",
        "LCPMT_YMD": "2020-01-01",
        "DTL_TASK_SE_NM": "동물병원",
    }
    result = parse_hospital_item(raw)
    assert result["name"] == "강남동물병원"
    assert result["status"] == "영업"
    assert result["region_city"] == "서울특별시"
    assert result["region_district"] == "강남구"
    assert result["type"] == "HOSPITAL"
    assert result["source_id"] == "HOSP-001"


def test_parse_hospital_item_missing_phone():
    raw = {
        "MNG_NO": "HOSP-002",
        "BPLC_NM": "테스트병원",
        "SALS_STTS_NM": "영업/정상",
        "ROAD_NM_ADDR": "경기도 수원시 어딘가 123",
        "TELNO": "",
        "LCPMT_YMD": "",
        "DTL_TASK_SE_NM": "",
    }
    result = parse_hospital_item(raw)
    assert result["phone"] is None
    assert result["license_no"] is None
    assert result["status"] == "영업"


def test_extract_hospitals_raises_on_api_error():
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
        extract_hospitals(bad_response)


@pytest.mark.asyncio
async def test_fetch_all_hospitals_collects_multiple_pages():
    page1 = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {
                "totalCount": 3,
                "items": {
                    "item": [
                        {"MNG_NO": "H1", "BPLC_NM": "A", "SALS_STTS_NM": "영업/정상", "ROAD_NM_ADDR": "서울 강남구 1"},
                        {"MNG_NO": "H2", "BPLC_NM": "B", "SALS_STTS_NM": "영업/정상", "ROAD_NM_ADDR": "서울 강남구 2"},
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
                    "item": {"MNG_NO": "H3", "BPLC_NM": "C", "SALS_STTS_NM": "폐업", "ROAD_NM_ADDR": "서울 강남구 3"}
                },
            },
        }
    }

    with patch("app.collector.hospital.fetch_hospitals", new=AsyncMock(side_effect=[page1, page2])) as mocked:
        rows = await fetch_all_hospitals(num_of_rows=2)

    assert len(rows) == 3
    assert rows[0]["status"] == "영업"
    assert rows[-1]["status"] == "폐업"
    assert mocked.await_count == 2
