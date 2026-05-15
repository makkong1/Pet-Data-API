"""서빙: Petory 등 클라이언트용 POST /recommend — DB·Redis 읽기 및 LLM 조합만. 수집 파이프라인과 분리 — docs/INGESTION-VS-SERVING.md."""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.platform.core.config import settings
from app.platform.core.database import get_db
from app.platform.core.auth import require_api_key
from app.platform.observability import get_request_id
from app.platform.schemas.recommend import (
    FacilityItem,
    RecommendCopyRequest,
    RecommendCopyResponse,
    RecommendRequest,
    RecommendResponse,
    TrendKeyword,
)
from app.serving.recommender.facilities import get_nearby_facilities, VALID_CONTEXTS, normalize_context
from app.serving.recommender.builder import build_prompt, build_trend_only_copy, build_context_copy
from app.serving.recommender.llm import generate_recommendation
from app.platform.cache.redis import get_trend
from app.ingestion.grooming_blog import extract_grooming_mentions, extract_context_mentions
from app.ingestion.kakao import search_kakao_places
from app.serving.recommender.grooming_ranker import rank_grooming_facilities
from app.serving.recommender.persistence import persist_recommendation_log
from app.serving.recommender.ranker import rank_facilities
from app.serving.recommender.signals.base import SignalContext

router = APIRouter(prefix="/recommend", tags=["추천 (Recommend)"])
ENRICHED_CONTEXTS = {"grooming", "hospital", "supplies"}

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
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    if req.context not in VALID_CONTEXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown context: {req.context}. Valid: {sorted(VALID_CONTEXTS)}",
        )

    request_id = get_request_id(request)
    normalized_context = normalize_context(req.context)
    trends_raw = await _load_trends_for_context(req.context, 10)
    trends = [TrendKeyword(keyword=k, score=int(s)) for k, s in trends_raw]

    recommend_version = "legacy"

    if normalized_context in ENRICHED_CONTEXTS and settings.GROOMING_MVP_ENABLED:
        # ── 컨텍스트 확장 파이프 (네이버 멘션 + Kakao POI) ──
        recommend_version = f"{normalized_context}-mvp-v1"
        radius_m = req.radius_km * 1000
        t_full = time.monotonic()
        req_id = request_id
        _log.info(
            "context_pipe [%s] start context=%s lat=%.5f lng=%.5f radius_km=%s top_n=%s",
            req_id,
            normalized_context,
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
            "context_pipe [%s] public_db context=%s count=%d elapsed_ms=%d",
            req_id,
            normalized_context,
            len(public_raw),
            int((time.monotonic() - t_db) * 1000),
        )

        # 블로그 멘션 추출 (실패 시 폴백: mention 없음)
        t_blog = time.monotonic()
        try:
            if normalized_context == "grooming":
                mention_map, candidate_names = await extract_grooming_mentions(req_id=req_id)
            else:
                mention_map, candidate_names = await extract_context_mentions(
                    normalized_context,
                    req_id=req_id,
                )
        except Exception:
            mention_map, candidate_names = {}, []
            _log.warning(
                "context_pipe [%s] context_blog_failed context=%s fallback empty mention",
                req_id,
                normalized_context,
            )
        blog_ms = int((time.monotonic() - t_blog) * 1000)

        candidate_count_raw = len(mention_map)
        candidate_count_after_cap = len(candidate_names)

        # Kakao 장소 검색 (실패 시 폴백: 공공만)
        t_kakao = time.monotonic()
        try:
            kakao_map = await search_kakao_places(
                candidate_names,
                req.lat,
                req.lng,
                context=normalized_context,
                req_id=req_id,
            )
        except Exception:
            kakao_map = {}
            _log.warning(
                "context_pipe [%s] kakao_search_failed context=%s fallback empty",
                req_id,
                normalized_context,
            )
        kakao_ms = int((time.monotonic() - t_kakao) * 1000)
        kakao_call_count = len(kakao_map)

        # 1차 dedupe·merge (공공 + Kakao + 멘션) — 후보를 넉넉히 유지.
        t_rank = time.monotonic()
        merged = rank_grooming_facilities(
            public_raw,
            kakao_map,
            mention_map,
            req.lat,
            req.lng,
            radius_m,
            req.top_n * 4,
            req_id=req_id,
        )
        # 2차 일반화 랭커 (신호 5종 가중합).
        signal_ctx = SignalContext(
            user_lat=req.lat,
            user_lng=req.lng,
            radius_m=radius_m,
            context=normalized_context,
            pet=req.pet.model_dump() if req.pet else None,
            db=db,
            trend_keywords={k: int(s) for k, s in trends_raw},
            request_id=req_id,
        )
        facilities_raw = await rank_facilities(merged, signal_ctx, top_n=req.top_n)
        rank_ms = int((time.monotonic() - t_rank) * 1000)
        total_ms = int((time.monotonic() - t_full) * 1000)

        _log.info(
            "context_pipe [%s] summary context=%s candidate_raw=%d after_cap=%d returned=%d "
            "kakao_keys=%d latency_total=%dms blog=%dms kakao=%dms rank=%dms",
            req_id,
            normalized_context,
            candidate_count_raw,
            candidate_count_after_cap,
            len(facilities_raw),
            kakao_call_count,
            total_ms,
            blog_ms,
            kakao_ms,
            rank_ms,
        )

        facilities = [
            FacilityItem(
                name=f["name"],
                distance_m=f["distance_m"],
                address=f["address"],
                lat=f.get("lat"),
                lng=f.get("lng"),
                mention_count=int(f.get("mention_count") or 0),
                mention_score=float(f.get("mention_score") or 0.0),
                source=f.get("source", "public"),
                score=float(f.get("score") or 0.0),
                reasons=list(f.get("reasons") or []),
            )
            for f in facilities_raw
        ]
        recommendation = build_context_copy(normalized_context, facilities_raw, trends_raw, req_id=req_id)
        _log.info(
            "context_pipe [%s] response context=%s facilities=%d recommend_len=%s",
            req_id,
            normalized_context,
            len(facilities),
            len(recommendation) if recommendation else 0,
        )

    else:
        # ── 레거시 파이프 (비그루밍 또는 플래그 off) ──
        public_raw = await get_nearby_facilities(
            db, req.lat, req.lng, normalized_context, req.radius_km, req.top_n
        )
        # facility_id·source_id 는 FacilityItem 에 노출하지 않음.
        facilities_raw = [
            {k: v for k, v in f.items() if k not in ("source_id", "facility_id")}
            for f in public_raw
        ]
        facilities = [FacilityItem(**f) for f in facilities_raw]

        if not facilities_raw and not trends_raw:
            recommendation = None
        elif req.include_copy:
            # 옵트인 LLM 경로 (기존 동작).
            if not facilities_raw and trends_raw:
                recommendation = build_trend_only_copy(normalized_context, trends_raw) or None
            else:
                pet_dict = req.pet.model_dump() if req.pet else None
                prompt = build_prompt(
                    normalized_context, facilities_raw,
                    [t.model_dump() for t in trends], pet_dict,
                )
                recommendation = await generate_recommendation(prompt)
        else:
            # 기본: 규칙 기반 카피만 (LLM 없음, p95 짧음).
            if not facilities_raw and trends_raw:
                recommendation = build_trend_only_copy(normalized_context, trends_raw) or None
            else:
                recommendation = build_context_copy(
                    normalized_context, facilities_raw, trends_raw, req_id=request_id,
                )

    # recommendation_log 적재 (실패해도 응답엔 영향 없음).
    await persist_recommendation_log(
        db,
        request_id=request_id,
        context=req.context,
        lat=req.lat,
        lng=req.lng,
        radius_km=req.radius_km,
        top_n=req.top_n,
        pet_payload=req.pet.model_dump() if req.pet else None,
        facility_ids=[
            (f.get("facility_id") if isinstance(f, dict) else None)
            for f in (facilities_raw if recommend_version != "legacy" else public_raw)
        ],
        facility_scores=[float(getattr(f, "score", 0.0)) for f in facilities],
        recommend_version=recommend_version,
    )

    response = RecommendResponse(
        context=req.context,
        recommend_version=recommend_version,
        request_id=request_id,
        facilities=facilities,
        trends=trends,
        recommendation=recommendation,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    _log.info("recommend response: %s", response.model_dump_json())
    return response


@router.post(
    "/copy",
    response_model=RecommendCopyResponse,
    summary="추천 카피만 별도 (LLM only)",
    description=(
        "POST /recommend 응답을 기반으로 LLM 추천 카피를 받는 보조 엔드포인트. "
        "본 추천 응답시간을 짧게 유지하기 위해 카피는 두 번째 콜로 비동기 수신하세요. "
        "LLM 다운/타임아웃 시 규칙 기반 카피로 폴백 (source='rule')."
    ),
)
async def recommend_copy(
    req: RecommendCopyRequest,
    request: Request,
    _: None = Depends(require_api_key),
) -> RecommendCopyResponse:
    request_id = req.request_id or get_request_id(request)
    normalized_context = normalize_context(req.context)

    facilities_dict = [
        {"name": f.name, "distance_m": int(f.distance_m or 0), "address": ""}
        for f in req.facilities
    ]
    trends_dict = [{"keyword": t.keyword, "score": int(t.score)} for t in req.trends]
    trends_tuples = [(t.keyword, int(t.score)) for t in req.trends]
    pet_dict = req.pet.model_dump() if req.pet else None

    if not facilities_dict and not trends_tuples:
        return RecommendCopyResponse(
            request_id=request_id,
            recommendation=None,
            source="rule",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    prompt = build_prompt(normalized_context, facilities_dict, trends_dict, pet_dict)
    recommendation = await generate_recommendation(prompt)
    source = "llm"

    if recommendation is None:
        # LLM 실패 시 규칙 기반 폴백.
        source = "rule"
        if facilities_dict:
            recommendation = build_context_copy(
                normalized_context, facilities_dict, trends_tuples, req_id=request_id,
            )
        else:
            recommendation = build_trend_only_copy(normalized_context, trends_tuples) or None

    return RecommendCopyResponse(
        request_id=request_id,
        recommendation=recommendation,
        source=source,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
