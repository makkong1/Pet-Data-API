from app.collector.hospital import parse_hospital_item


def test_parse_hospital_item_maps_fields():
    raw = {
        "bplcNm": "강남동물병원",
        "dtlStateNm": "영업",
        "rdnAdr": "서울특별시 강남구 봉은사로 123",
        "ctpvNm": "서울특별시",
        "signguNm": "강남구",
        "siteTel": "02-9876-5432",
        "mgtNo": "HOSP-001",
        "uptaeNm": "동물병원",
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
        "bplcNm": "테스트병원",
        "dtlStateNm": "영업",
        "rdnAdr": "경기도 수원시 어딘가",
        "ctpvNm": "경기도",
        "signguNm": "수원시",
        "mgtNo": "HOSP-002",
        "uptaeNm": "동물병원",
    }
    result = parse_hospital_item(raw)
    assert result["phone"] is None
    assert result["license_no"] is None
