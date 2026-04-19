import pytest
from app.collector.parser import parse_animal_item


def test_parse_animal_item_maps_fields():
    raw = {
        "noticeNo": "충남-천안-2024-00001",
        "upKindNm": "개",
        "kindNm": "믹스견",
        "age": "2023(년생)",
        "sexCd": "M",
        "orgNm": "충남 천안시",
        "careNm": "천안시보호소",
        "processState": "보호중",
        "noticeSdt": "20240101",
    }
    result = parse_animal_item(raw)
    assert result["notice_no"] == "충남-천안-2024-00001"
    assert result["animal_type"] == "개"
    assert result["breed"] == "믹스견"
    assert result["gender"] == "M"
    assert result["status"] == "보호중"


def test_parse_animal_item_missing_field_returns_none():
    raw = {"noticeNo": "test-001"}
    result = parse_animal_item(raw)
    assert result["notice_no"] == "test-001"
    assert result["breed"] is None
