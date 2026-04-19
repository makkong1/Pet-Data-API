from app.collector.hospital import parse_hospital_item


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
    assert result["status"] == "영업/정상"
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
