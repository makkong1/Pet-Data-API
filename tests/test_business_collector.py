from app.collector.business import parse_business_item


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
    assert result["status"] == "영업/정상"
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
