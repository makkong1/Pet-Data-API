import pytest
from app.ingestion.exporter import _coord, parse_address_parts, popular_dict_to_dto


# ── _coord ────────────────────────────────────────────────────────────

def test_coord_converts_naver_mapy_to_lat():
    assert _coord("375000000") == pytest.approx(37.5)


def test_coord_converts_naver_mapx_to_lng():
    assert _coord("1270000000") == pytest.approx(127.0)


def test_coord_returns_none_for_empty_string():
    assert _coord("") is None


def test_coord_returns_none_for_none():
    assert _coord(None) is None


def test_coord_returns_none_for_zero():
    assert _coord("0") is None


# ── parse_address_parts ───────────────────────────────────────────────

def test_parse_address_parts_standard():
    sido, sigungu = parse_address_parts("서울특별시 강남구 테헤란로 123")
    assert sido == "서울특별시"
    assert sigungu == "강남구"


def test_parse_address_parts_none_input():
    assert parse_address_parts(None) == (None, None)


def test_parse_address_parts_empty_string():
    assert parse_address_parts("") == (None, None)


def test_parse_address_parts_single_token():
    sido, sigungu = parse_address_parts("서울특별시")
    assert sido == "서울특별시"
    assert sigungu is None


# ── popular_dict_to_dto ───────────────────────────────────────────────

def test_popular_dict_to_dto_blog_entry():
    d = {
        "name":         "멍멍미용",
        "mention_count": 3,
        "score":        1.0,
        "address":      "서울특별시 강남구 역삼동 1",
        "road_address": None,
        "map_x":        "1270000000",
        "map_y":        "375000000",
        "telephone":    "02-1234-5678",
    }
    dto = popular_dict_to_dto(d, "grooming")
    assert dto["name"]     == "멍멍미용"
    assert dto["category"] == "grooming"
    assert dto["address"]  == "서울특별시 강남구 역삼동 1"
    assert dto["sido"]     == "서울특별시"
    assert dto["sigungu"]  == "강남구"
    assert dto["lat"]      == pytest.approx(37.5)
    assert dto["lng"]      == pytest.approx(127.0)
    assert dto["phone"]    == "02-1234-5678"
    assert dto["status"]   == "운영중"


def test_popular_dict_to_dto_prefers_road_address():
    d = {
        "name":         "멍멍미용",
        "address":      "서울특별시 강남구 역삼동 1",
        "road_address": "서울특별시 강남구 테헤란로 1",
        "map_x": None, "map_y": None, "telephone": None,
    }
    dto = popular_dict_to_dto(d, "grooming")
    assert dto["address"] == "서울특별시 강남구 테헤란로 1"


def test_popular_dict_to_dto_no_coords():
    d = {
        "name": "멍멍미용", "address": "서울특별시 강남구 역삼동 1",
        "road_address": None, "map_x": None, "map_y": None, "telephone": None,
    }
    dto = popular_dict_to_dto(d, "grooming")
    assert dto["lat"] is None
    assert dto["lng"] is None
