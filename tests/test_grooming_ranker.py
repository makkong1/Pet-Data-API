import pytest
from app.serving.recommender.grooming_ranker import (
    haversine_m,
    _is_same_facility,
    rank_grooming_facilities,
)

USER_LAT, USER_LNG = 37.5665, 126.978
RADIUS_M = 3000.0


def test_haversine_same_point():
    assert haversine_m(37.5, 126.9, 37.5, 126.9) == pytest.approx(0.0, abs=1.0)


def test_haversine_known_distance():
    # 서울 시청 → 광화문 약 600~1200m
    d = haversine_m(37.5665, 126.9780, 37.5759, 126.9769)
    assert 500 < d < 1500


def test_is_same_facility_similar():
    assert _is_same_facility("해피독미용실", "해피독 미용실") is True


def test_is_same_facility_different():
    assert _is_same_facility("해피독", "행복한강아지") is False


def test_rank_public_only():
    public = [
        {"source_id": "A001", "name": "해피독", "address": "서울", "lat": 37.5665, "lng": 126.979, "distance_m": 100},
        {"source_id": "A002", "name": "멍멍샵", "address": "서울", "lat": 37.567, "lng": 126.980, "distance_m": 500},
    ]
    result = rank_grooming_facilities(public, {}, {}, USER_LAT, USER_LNG, RADIUS_M, top_n=5)
    assert len(result) == 2
    assert result[0]["name"] == "해피독"
    assert result[0]["source"] == "public"
    assert 0.0 <= result[0]["score"] <= 1.0
    assert result[0]["mention_count"] == 0
    assert result[0]["mention_score"] == 0.0


def test_rank_kakao_outside_radius_excluded():
    public = []
    kakao_map = {
        "해피독": [{"name": "해피독", "address": "경기", "lat": 37.7, "lng": 127.1}]
    }
    # 37.7, 127.1은 서울 시청(37.5665, 126.978)에서 약 20km 이상
    result = rank_grooming_facilities(public, kakao_map, {}, USER_LAT, USER_LNG, RADIUS_M, top_n=5)
    assert len(result) == 0


def test_rank_public_kakao_merge():
    """공공 DB와 Kakao POI가 동일 업장이면 병합 — 공공 좌표·주소 우선."""
    public = [
        {"source_id": "A001", "name": "해피독미용실", "address": "서울 강남", "lat": 37.5665, "lng": 126.979, "distance_m": 100},
    ]
    kakao_map = {
        "해피독 미용실": [{"name": "해피독 미용실", "address": "서울 강남구", "lat": 37.5666, "lng": 126.9791}]
    }
    mention_map = {"해피독 미용실": {"count": 5, "freshness": 0.8}}
    result = rank_grooming_facilities(public, kakao_map, mention_map, USER_LAT, USER_LNG, RADIUS_M, top_n=5)
    assert len(result) == 1
    assert result[0]["source"] == "public+kakao"
    assert result[0]["mention_count"] == 5
    assert result[0]["address"] == "서울 강남"  # 공공 주소 우선


def test_rank_dedup_same_name():
    """중복 이름 후보가 있으면 1개만."""
    public = [
        {"source_id": "A001", "name": "해피독", "address": "서울", "lat": 37.5665, "lng": 126.979, "distance_m": 100},
    ]
    kakao_map = {
        "해피독": [{"name": "해피독", "address": "서울", "lat": 37.5665, "lng": 126.979}]
    }
    result = rank_grooming_facilities(public, kakao_map, {}, USER_LAT, USER_LNG, RADIUS_M, top_n=5)
    assert len(result) == 1


def test_rank_score_normalized():
    """모든 score·mention_score 값이 [0.0, 1.0] 범위."""
    public = [
        {"source_id": f"X{i}", "name": f"미용실{i}", "address": "서울", "lat": 37.5665 + i * 0.001, "lng": 126.978, "distance_m": i * 100}
        for i in range(5)
    ]
    mention_map = {f"미용실{i}": {"count": i * 2, "freshness": i * 0.1} for i in range(5)}
    result = rank_grooming_facilities(public, {}, mention_map, USER_LAT, USER_LNG, RADIUS_M, top_n=5)
    for r in result:
        assert 0.0 <= r["score"] <= 1.0
        assert 0.0 <= r["mention_score"] <= 1.0


def test_rank_top_n_limit():
    """top_n 이하로 반환."""
    public = [
        {"source_id": f"X{i}", "name": f"미용실{i}", "address": "서울", "lat": 37.566 + i * 0.0001, "lng": 126.978, "distance_m": i * 50}
        for i in range(10)
    ]
    result = rank_grooming_facilities(public, {}, {}, USER_LAT, USER_LNG, RADIUS_M, top_n=3)
    assert len(result) == 3
