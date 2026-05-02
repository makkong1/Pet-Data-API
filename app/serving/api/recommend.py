"""서빙: Petory 등 클라이언트용 POST /recommend — DB·Redis 읽기 및 LLM 조합만. 수집 파이프라인과 분리 — docs/INGESTION-VS-SERVING.md."""

import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.platform.core.config import settings
from app.platform.core.database import get_db
from app.platform.core.auth import require_api_key
from app.platform.schemas.recommend import RecommendRequest, RecommendResponse, FacilityItem, TrendKeyword
from app.serving.recommender.facilities import get_nearby_facilities, VALID_CONTEXTS, normalize_context
from app.serving.recommender.builder import build_prompt, build_trend_only_copy, build_grooming_copy
from app.serving.recommender.llm import generate_recommendation
from app.platform.cache.redis import get_trend
from app.ingestion.grooming_blog import extract_grooming_mentions
from app.ingestion.kakao import search_kakao_places
from app.serving.recommender.grooming_ranker import rank_grooming_facilities

router = APIRouter(prefix="/recommend", tags=["추천 (Recommend)"])

_log = logging.getLogger(__name__)
if not _log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False


async def _load_trends_for_context(context: str, limit: int = 10) -> list[tuple[str, int]]:
    normalized = normalize_context(context)
    categories = [normalized]
    if normalized == "supplies":
        categories = ["supplies", "snack", "food", "clothes"]

    scores: dict[str, int] = defaultdict(int)
    for category in categories:
        try:
            trend_rows = await get_trend(category, limit)
        except Exception:
            continue
        for keyword, score in trend_rows:
            scores[keyword] += int(score)

    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_items[:limit]


@router.post(
    "",
    response_model=RecommendResponse,
    summary="맞춤 추천 (Recommend)",
    description="근처 시설(DB)·트렌드(Redis). 시설 없을 때는 LLM 없이 트렌드 키워드 안내만. "
    "(Facilities from DB, trends from Redis; no LLM when no facilities.)",
)
async def recommend(
    req: RecommendRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    if req.context not in VALID_CONTEXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown context: {req.context}. Valid: {sorted(VALID_CONTEXTS)}",
        )

    normalized_context = normalize_context(req.context)
    trends_raw = await _load_trends_for_context(req.context, 10)
    trends = [TrendKeyword(keyword=k, score=int(s)) for k, s in trends_raw]

    recommend_version = "legacy"

    if req.context == "grooming" and settings.GROOMING_MVP_ENABLED:
        # ── 그루밍 MVP 파이프 (§1.1) ──
        recommend_version = "grooming-mvp-v1"
        radius_m = req.radius_km * 1000
        t_full = time.monotonic()
        req_id = uuid.uuid4().hex[:10]
        _log.info(
            "grooming_pipe [%s] start context=grooming lat=%.5f lng=%.5f radius_km=%s top_n=%s",
            req_id,
            req.lat,
            req.lng,
            req.radius_km,
            req.top_n,
        )

        # 공공 DB 반경 목록 (source_id 포함, 여유있게 4배 조회 후 랭커에서 top_n으로 자름)
        t_db = time.monotonic()
        public_raw = await get_nearby_facilities(
            db, req.lat, req.lng, normalized_context, req.radius_km, req.top_n * 4
        )
        _log.info(
            "grooming_pipe [%s] public_db count=%d elapsed_ms=%d",
            req_id,
            len(public_raw),
            int((time.monotonic() - t_db) * 1000),
        )

        # 블로그 멘션 추출 (실패 시 폴백: mention 없음)
        t_blog = time.monotonic()
        try:
            mention_map, candidate_names = await extract_grooming_mentions(req_id=req_id)
        except Exception:
            mention_map, candidate_names = {}, []
            _log.warning("grooming_pipe [%s] grooming_blog_failed: fallback empty mention", req_id)
        blog_ms = int((time.monotonic() - t_blog) * 1000)

        candidate_count_raw = len(mention_map)
        candidate_count_after_cap = len(candidate_names)

        # Kakao 장소 검색 (실패 시 폴백: 공공만)
        t_kakao = time.monotonic()
        try:
            kakao_map = await search_kakao_places(candidate_names, req.lat, req.lng, req_id=req_id)
        except Exception:
            kakao_map = {}
            _log.warning("grooming_pipe [%s] kakao_search_failed: fallback empty", req_id)
        kakao_ms = int((time.monotonic() - t_kakao) * 1000)
        kakao_call_count = len(kakao_map)

        # 랭킹 & dedupe
        t_rank = time.monotonic()
        facilities_raw = rank_grooming_facilities(
            public_raw,
            kakao_map,
            mention_map,
            req.lat,
            req.lng,
            radius_m,
            req.top_n,
            req_id=req_id,
        )
        rank_ms = int((time.monotonic() - t_rank) * 1000)
        total_ms = int((time.monotonic() - t_full) * 1000)

        _log.info(
            "grooming_pipe [%s] summary candidate_raw=%d after_cap=%d returned=%d "
            "kakao_keys=%d latency_total=%dms blog=%dms kakao=%dms rank=%dms",
            req_id,
            candidate_count_raw,
            candidate_count_after_cap,
            len(facilities_raw),
            kakao_call_count,
            total_ms,
            blog_ms,
            kakao_ms,
            rank_ms,
        )

        facilities = [FacilityItem(**{k: v for k, v in f.items()}) for f in facilities_raw]
        recommendation = build_grooming_copy(facilities_raw, trends_raw, req_id=req_id)
        _log.info(
            "grooming_pipe [%s] response facilities=%d recommend_len=%s",
            req_id,
            len(facilities),
            len(recommendation) if recommendation else 0,
        )

    else:
        # ── 레거시 파이프 (비그루밍 또는 플래그 off) ──
        public_raw = await get_nearby_facilities(
            db, req.lat, req.lng, normalized_context, req.radius_km, req.top_n
        )
        # source_id는 FacilityItem 스키마에 없으므로 제거
        facilities_raw = [{k: v for k, v in f.items() if k != "source_id"} for f in public_raw]
        facilities = [FacilityItem(**f) for f in facilities_raw]

        if not facilities_raw and not trends_raw:
            recommendation = None
        elif not facilities_raw and trends_raw:
            recommendation = build_trend_only_copy(normalized_context, trends_raw) or None
        else:
            pet_dict = req.pet.model_dump() if req.pet else None
            prompt = build_prompt(normalized_context, facilities_raw, [t.model_dump() for t in trends], pet_dict)
            recommendation = await generate_recommendation(prompt)

    response = RecommendResponse(
        context=req.context,
        recommend_version=recommend_version,
        facilities=facilities,
        trends=trends,
        recommendation=recommendation,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    _log.info("recommend response: %s", response.model_dump_json())
    return response
