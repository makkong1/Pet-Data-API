import logging
import math
import re
from typing import Optional

from rapidfuzz import fuzz

# §2.3 유사도 임계값 — SSOT (docs/GROOMING-RECOMMEND-MVP.md §2.3)
_SIMILARITY_THRESHOLD = 85  # RapidFuzz ratio 기준

# §2.8 점수 가중치 (합 = 1.0)
_W_DISTANCE = 0.5
_W_MENTION = 0.3
_W_FRESHNESS = 0.2

_log = logging.getLogger(__name__)


def _normalize_for_match(name: str) -> str:
    """병합 비교용 정규화: 공백·특수문자 제거, 소문자."""
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
    req_id: Optional[str] = None,
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
    rid = req_id or "-"
    _log.info(
        "grooming_ranker [%s] start public=%d kakao_keys=%d mention=%d radius_m=%.0f top_n=%d",
        rid,
        len(public_facilities),
        len(kakao_map),
        len(mention_map),
        radius_m,
        top_n,
    )
    # ── 1. 공공 시설 목록 (이미 반경 필터 완료, distance_m 있음)
    candidates: list[dict] = []

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
                if c["public_matched"] and _is_same_facility(c["name"], place["name"]):
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

    _log.info("grooming_ranker [%s] after_merge candidates=%d", rid, len(candidates))

    # ── 3. 중복 제거: 정규화 이름 기준
    deduped: list[dict] = []
    seen_norms: set[str] = set()
    for c in candidates:
        norm = _normalize_for_match(c["name"])
        if norm in seen_norms:
            continue
        seen_norms.add(norm)
        deduped.append(c)

    by_source = {"public": 0, "public+kakao": 0, "kakao": 0}
    for c in deduped:
        src = c.get("source", "")
        if src in by_source:
            by_source[src] += 1

    _log.info(
        "grooming_ranker [%s] after_dedupe count=%d by_source=%s",
        rid,
        len(deduped),
        by_source,
    )

    # ── 4. 정렬 §2.3 (거리↑ → 공공매칭 있는 것↑ → mention_count↓ → source_id/name↑)
    deduped.sort(key=lambda c: (
        c["distance_m"],
        0 if c["public_matched"] else 1,
        -c["mention_count"],
        c["source_id"] or c["name"],
    ))

    # ── 5. score · mention_score 정규화 [0.0, 1.0] (§2.8)
    max_dist = max((c["distance_m"] for c in deduped), default=1) or 1
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

    out_sources = {"public": 0, "public+kakao": 0, "kakao": 0}
    for row in result:
        s = row.get("source", "")
        if s in out_sources:
            out_sources[s] += 1
    _log.info(
        "grooming_ranker [%s] result top=%d by_source=%s",
        rid,
        len(result),
        out_sources,
    )

    return result
