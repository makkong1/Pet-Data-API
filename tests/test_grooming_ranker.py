import pytest
from app.serving.recommender.grooming_ranker import (
    haversine_m,
    _is_same_facility,
    _is_mention_of_facility,
    _might_be_same_facility,
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


def test_might_be_same_facility_prefix():
    """한쪽이 다른 쪽 prefix면 True."""
    assert _might_be_same_facility("꾸러미세상", "꾸러미세상 애견용품") is True
    assert _might_be_same_facility("꾸러미세상 애견용품", "꾸러미세상") is True


def test_might_be_same_facility_different():
    """완전히 다른 이름은 False."""
    assert _might_be_same_facility("꾸러미세상", "행복강아지미용실") is False


def test_rank_dedup_public_name_kakao_longer_name():
    """공공 DB 약식명(꾸러미세상) vs Kakao 정식명(꾸러미세상 애견용품) — 1개만 반환, 공공 우선."""
    # P1 재현: public 409m(주소없음) + Kakao standalone 1110m(주소있음)
    public = [
        {
            "source_id": "B001", "name": "꾸러미세상", "address": "",
            "lat": 37.6129, "lng": 127.0775, "distance_m": 409,
        }
    ]
    kakao_map = {
        "꾸러미세상": [
            {
                "name": "꾸러미세상 애견용품",
                "address": "서울 중랑구 봉화산로 115",
                "lat": 37.6194, "lng": 127.0819,
            }
        ]
    }
    mention_map = {"꾸러미세상": {"count": 6, "freshness": 0.5}}
    result = rank_grooming_facilities(
        public, kakao_map, mention_map, USER_LAT, USER_LNG, radius_m=10000.0, top_n=5
    )
    names = [r["name"] for r in result]
    # 중복 없이 1개만
    assert sum(1 for n in names if "꾸러미세상" in n) == 1
    # 공공 데이터 우선 — distance_m이 Kakao standalone(1110m)이 아닌 공공값(409m)
    kuru = next(r for r in result if "꾸러미세상" in r["name"])
    assert kuru["distance_m"] == 409
    assert kuru["mention_count"] == 6


def test_hospital_excluded_from_grooming():
    """병원·의원·클리닉 이름 시설은 grooming 결과에서 제외."""
    public = [
        {"source_id": "H001", "name": "우솔동물병원", "address": "서울", "lat": 37.5665, "lng": 126.979, "distance_m": 200},
        {"source_id": "A001", "name": "해피독미용실", "address": "서울", "lat": 37.5667, "lng": 126.979, "distance_m": 300},
        {"source_id": "H002", "name": "행복동물의원", "address": "서울", "lat": 37.5668, "lng": 126.979, "distance_m": 400},
    ]
    result = rank_grooming_facilities(public, {}, {}, USER_LAT, USER_LNG, RADIUS_M, top_n=5)
    names = [r["name"] for r in result]
    assert "우솔동물병원" not in names
    assert "행복동물의원" not in names
    assert "해피독미용실" in names


def test_hospital_kakao_excluded_from_grooming():
    """Kakao 단독 후보에서도 병원명은 제외."""
    kakao_map = {
        "우솔동물병원": [{"name": "우솔동물병원", "address": "서울", "lat": 37.5665, "lng": 126.979}],
        "예쁜미용실": [{"name": "예쁜미용실", "address": "서울", "lat": 37.5666, "lng": 126.979}],
    }
    result = rank_grooming_facilities([], kakao_map, {}, USER_LAT, USER_LNG, RADIUS_M, top_n=5)
    names = [r["name"] for r in result]
    assert "우솔동물병원" not in names
    assert "예쁜미용실" in names


# ── _is_mention_of_facility 단위 테스트 ──

def test_is_mention_of_facility_prefix_match():
    """짧은 멘션(니니)이 정식명(니니 애견 미용실)에 포함되면 True."""
    assert _is_mention_of_facility("니니", "니니 애견 미용실") is True


def test_is_mention_of_facility_same_length_rejected():
    """정식명과 길이 차이가 작으면 False (우연한 포함 방지)."""
    assert _is_mention_of_facility("니니", "니니샵") is False


def test_is_mention_of_facility_unrelated_false():
    """관련 없는 이름은 False."""
    assert _is_mention_of_facility("루비", "니니 애견 미용실") is False


def test_is_mention_of_facility_too_short_false():
    """1자 멘션은 False."""
    assert _is_mention_of_facility("니", "니니 애견 미용실") is False


# ── 니니 → "니니 애견 미용실" 실제 매핑 시나리오 ──

def test_nini_mention_maps_to_facility():
    """블로그 멘션 '니니'가 공공 DB '니니 애견 미용실'에 매핑되어 mention_count가 반영된다."""
    public = [
        {
            "source_id": "N001", "name": "니니 애견 미용실", "address": "서울",
            "lat": 37.5665, "lng": 126.979, "distance_m": 500,
        }
    ]
    mention_map = {"니니": {"count": 3, "freshness": 0.7}}
    result = rank_grooming_facilities(public, {}, mention_map, USER_LAT, USER_LNG, RADIUS_M, top_n=5)
    assert len(result) == 1
    assert result[0]["name"] == "니니 애견 미용실"
    assert result[0]["mention_count"] == 3
    assert result[0]["source"] == "public+kakao"


def test_kakao_name_mismatch_no_mention_propagation():
    """Kakao 반환 업체명이 블로그 후보명과 다를 때 mention_count를 이관하지 않는다.

    실제 관찰 케이스: 블로그 후보 '해피독' 검색 → Kakao '강아지미용실' 반환.
    '강아지미용실'은 '해피독'과 무관한 업체이므로 mention_count=0이어야 함.
    """
    mention_map = {"해피독": {"count": 5, "freshness": 0.9}}
    kakao_map = {
        "해피독": [{"name": "강아지미용실", "address": "서울 중랑구 중랑역로 226", "lat": 37.613, "lng": 127.075}]
    }
    result = rank_grooming_facilities(
        public_facilities=[],
        kakao_map=kakao_map,
        mention_map=mention_map,
        user_lat=37.610,
        user_lng=127.070,
        radius_m=3000,
        top_n=5,
    )
    assert len(result) == 1
    assert result[0]["name"] == "강아지미용실"
    assert result[0]["mention_count"] == 0


def test_kakao_name_match_mention_propagated():
    """Kakao 반환 업체명이 블로그 후보명과 유사하면 mention_count가 이관된다."""
    mention_map = {"해피독미용실": {"count": 4, "freshness": 0.8}}
    kakao_map = {
        "해피독미용실": [{"name": "해피독 미용실", "address": "서울 강남구", "lat": 37.567, "lng": 126.979}]
    }
    result = rank_grooming_facilities(
        public_facilities=[],
        kakao_map=kakao_map,
        mention_map=mention_map,
        user_lat=USER_LAT,
        user_lng=USER_LNG,
        radius_m=RADIUS_M,
        top_n=5,
    )
    assert len(result) == 1
    assert result[0]["mention_count"] == 4
