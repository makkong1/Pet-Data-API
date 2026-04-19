from app.collector.business import parse_business_item


def test_parse_business_item_maps_fields():
    raw = {
        "bsnNm": "행복 펫 미용",
        "bsnStts": "영업",
        "rdnAdr": "서울특별시 강남구 테헤란로 123",
        "ctpvNm": "서울특별시",
        "signguNm": "강남구",
        "telNo": "02-1234-5678",
        "mgtNo": "BIZ-001",
        "uptaeNm": "동물미용업",
    }
    result = parse_business_item(raw)
    assert result["name"] == "행복 펫 미용"
    assert result["status"] == "영업"
    assert result["region_city"] == "서울특별시"
    assert result["region_district"] == "강남구"
    assert result["type"] == "BUSINESS"
    assert result["business_type"] == "동물미용업"


def test_parse_business_item_missing_phone():
    raw = {
        "bsnNm": "테스트",
        "bsnStts": "영업",
        "rdnAdr": "서울특별시 강남구 어딘가",
        "ctpvNm": "서울특별시",
        "signguNm": "강남구",
        "mgtNo": "BIZ-002",
        "uptaeNm": "동물위탁관리업",
    }
    result = parse_business_item(raw)
    assert result["phone"] is None
    assert result["source_id"] == "BIZ-002"
