# Step 4 — 랭킹 & Dedupe 엔진

## 목적
공공 DB 시설 목록 + Kakao POI 후보 + 블로그 멘션 정보 → 랭킹·중복 제거 → 최종 시설 목록 생성.  
`score`와 `mention_score`는 [0.0, 1.0]으로 정규화해서 반환한다.

## 배경
- SSOT: `docs/GROOMING-RECOMMEND-MVP.md` §2.3, §2.4, §2.8
- 공공 `pet_facilities`는 신뢰 소스 — 좌표·주소는 공공 DB 우선. Kakao는 멘션·거리 보조 신호.
- RapidFuzz `ratio` 임계값 **85** (상수로 코드에 박음). `rapidsearch`가 아닌 `rapidfuzz.fuzz.ratio`.
- `source` 값: `"public"` | `"kakao"` | `"public+kakao"`.

## 사전 준비: `app/serving/recommender/facilities.py` SQL 수정

현재 SQL에서 `source_id`를 반환하지 않는다. 아래와 같이 수정한다.

### `_HAVERSINE_SQL` 변경
```python
_HAVERSINE_SQL = """
WITH distances AS (
    SELECT
        source_id,
        name,
        address,
        lat,
        lng,
        6371000 * acos(
            LEAST(1.0,
                cos(radians(:lat)) * cos(radians(lat)) *
                cos(radians(lng) - radians(:lng)) +
                sin(radians(:lat)) * sin(radians(lat))
            )
        ) AS distance_m
    FROM pet_facilities
    WHERE lat IS NOT NULL
      AND type = :ftype
)
SELECT source_id, name, address, lat, lng, distance_m
FROM distances
WHERE distance_m <= :radius_m
ORDER BY distance_m
LIMIT :top_n
"""
```

### `get_nearby_facilities` 반환값에 `source_id` 추가
```python
return [
    {
        "source_id": r["source_id"],
        "name": r["name"],
        "distance_m": int(r["distance_m"]),
        "address": r["address"],
        "lat": r.get("lat"),
        "lng": r.get("lng"),
    }
    for r in rows
]
```

기존 `FacilityItem` 스키마에 `source_id`가 없으므로, 핸들러에서 직접 `source_id`를 pop 처리하거나 Step 5 스키마 확장 시 함께 처리한다.

## 생성할 파일: `app/serving/recommender/grooming_ranker.py`

```python
import math
import re
from typing import Optional

# rapidfuzz는 requirements.txt에 있어야 함. 없으면: pip install rapidfuzz
from rapidfuzz import fuzz

# §2.3 유사도 임계값 (상수)
_SIMILARITY_THRESHOLD = 85  # RapidFuzz ratio 기준

# §2.8 점수 가중치 (env로 빼기 어려우므로 상수 — 튜닝 시 여기만 수정)
_W_DISTANCE = 0.5
_W_MENTION = 0.3
_W_FRESHNESS = 0.2


def _normalize_for_match(name: str) -> str:
    """병합 비교용 정규화: 공백·특수문자·조사 제거, 소문자."""
    return re.sub(r"[^가-힣a-z0-9]", "", name.lower())


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 Haversine 거리 (미터)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _is_same_facility(name_a: str, name_b: str) -> bool:
    """두 상호명이 동일 업장인지 판단. §2.3"""
    na, nb = _normalize_for_match(name_a), _normalize_for_match(name_b)
    return fuzz.ratio(na, nb) >= _SIMILARITY_THRESHOLD


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def rank_grooming_facilities(
    public_facilities: list[dict],
    kakao_map: dict[str, list[dict]],
    mention_map: dict[str, dict],
    user_lat: float,
    user_lng: float,
    radius_m: float,
    top_n: int,
) -> list[dict]:
    """
    공공 DB + Kakao POI → 랭킹·병합·dedupe → top_n 개 반환.

    Args:
        public_facilities: get_nearby_facilities() 반환값 (source_id 포함).
        kakao_map: search_kakao_places() 반환값 {candidate_name: [place_dict]}.
        mention_map: extract_grooming_mentions() 반환값 {name: {"count": int, "freshness": float}}.
        user_lat, user_lng: 사용자 좌표.
        radius_m: 반경 (미터).
        top_n: 최종 반환 수 상한.
    """
    # ── 1. 공공 시설 목록 (이미 반경 필터 완료, distance_m 있음)
    candidates: list[dict] = []
    seen_source_ids: set[str] = set()

    for pf in public_facilities:
        entry = {
            "name": pf["name"],
            "address": pf["address"],
            "lat": pf.get("lat"),
            "lng": pf.get("lng"),
            "distance_m": pf["distance_m"],
            "source_id": pf.get("source_id", ""),
            "source": "public",
            "mention_count": 0,
            "freshness": 0.0,
            "public_matched": True,
        }
        # 블로그 멘션 매핑 시도
        for m_name, m_info in mention_map.items():
            if _is_same_facility(pf["name"], m_name):
                entry["mention_count"] = m_info["count"]
                entry["freshness"] = m_info["freshness"]
                entry["source"] = "public+kakao"
                break
        candidates.append(entry)
        seen_source_ids.add(pf.get("source_id", ""))

    # ── 2. Kakao POI를 반경 재검증 후 공공 병합 or 독립 추가
    for candidate_name, places in kakao_map.items():
        for place in places:
            if place.get("lat") is None or place.get("lng") is None:
                continue
            dist = haversine_m(user_lat, user_lng, place["lat"], place["lng"])
            if dist > radius_m:
                continue  # §2.3 반경 밖 즉시 제외

            # 공공 DB에 동일 시설이 있는지 확인
            matched_public = None
            for c in candidates:
                if c["source"] in ("public", "public+kakao") and _is_same_facility(c["name"], place["name"]):
                    matched_public = c
                    break

            if matched_public:
                # 공공과 병합 — 좌표·주소는 공공 우선, 멘션만 보강
                m_info = mention_map.get(candidate_name, {})
                if m_info:
                    matched_public["mention_count"] = max(
                        matched_public["mention_count"], m_info["count"]
                    )
                    matched_public["freshness"] = max(
                        matched_public["freshness"], m_info["freshness"]
                    )
                    matched_public["source"] = "public+kakao"
            else:
                # Kakao 단독 후보
                m_info = mention_map.get(candidate_name, {})
                entry = {
                    "name": place["name"],
                    "address": place["address"],
                    "lat": place["lat"],
                    "lng": place["lng"],
                    "distance_m": int(dist),
                    "source_id": "",
                    "source": "kakao",
                    "mention_count": m_info.get("count", 0),
                    "freshness": m_info.get("freshness", 0.0),
                    "public_matched": False,
                }
                candidates.append(entry)

    # ── 3. 중복 제거: 동일 source_id 또는 동명 병합 판정
    deduped: list[dict] = []
    seen_names: set[str] = set()
    for c in candidates:
        norm = _normalize_for_match(c["name"])
        if norm in seen_names:
            continue
        seen_names.add(norm)
        deduped.append(c)

    # ── 4. 정렬 §2.3 (거리↑ → 공공매칭↓ → mention_count↓ → source_id/name↑)
    deduped.sort(key=lambda c: (
        c["distance_m"],
        0 if c["public_matched"] else 1,
        -c["mention_count"],
        c["source_id"] or c["name"],
    ))

    # ── 5. score · mention_score 정규화 [0.0, 1.0] (§2.8)
    max_dist = max((c["distance_m"] for c in deduped), default=1)
    max_mention = max((c["mention_count"] for c in deduped), default=1) or 1

    result: list[dict] = []
    for c in deduped[:top_n]:
        dist_score = _clamp01(1.0 - c["distance_m"] / max_dist)
        mention_score = _clamp01(c["mention_count"] / max_mention)
        freshness_score = _clamp01(c["freshness"])
        score = _clamp01(
            _W_DISTANCE * dist_score
            + _W_MENTION * mention_score
            + _W_FRESHNESS * freshness_score
        )
        result.append({
            "name": c["name"],
            "address": c["address"],
            "lat": c.get("lat"),
            "lng": c.get("lng"),
            "distance_m": c["distance_m"],
            "source": c["source"],
            "mention_count": c["mention_count"],
            "mention_score": round(mention_score, 4),
            "score": round(score, 4),
        })

    return result
```

## 생성할 파일: `tests/test_grooming_ranker.py`

```python
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
    # 서울 시청 → 광화문 약 600m
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
    """공공 DB와 Kakao POI가 동일 업장이면 병합 — 공공 좌표 우선."""
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
```

## 완료 기준 (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate

# rapidfuzz 설치 확인
pip show rapidfuzz || pip install rapidfuzz

pytest tests/test_grooming_ranker.py -v
# 모든 테스트 PASSED
```

## 주의
- `rapidfuzz`가 `requirements.txt`에 없으면 추가한다.
- `_SIMILARITY_THRESHOLD = 85`는 주석에 "§2.3 SSOT"를 명시한다.
- 점수 가중치 3개의 합이 1.0이어야 한다 (`_W_DISTANCE + _W_MENTION + _W_FRESHNESS == 1.0`).
- 공공 DB의 `source_id` 반환을 위해 `app/serving/recommender/facilities.py` SQL을 이 Step에서 함께 수정한다.
