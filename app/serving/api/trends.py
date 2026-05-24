import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from redis.exceptions import RedisError
from app.platform.cache.redis import get_trend, get_updated_at
from app.platform.core.auth import require_api_key
from app.platform import integration_trace
from app.ingestion.naver import CATEGORY_KEYWORDS
from app.platform.observability import get_request_id

router = APIRouter(prefix="/trends", tags=["트렌드 (Trends)"])
_log = logging.getLogger(__name__)

VALID_CATEGORIES = set(CATEGORY_KEYWORDS.keys())


@router.get(
    "/{category}",
    summary="카테고리별 트렌드 (Trends by category)",
    description="Redis에 캐시된 키워드 순위. (Keyword rankings from Redis cache.)",
)
async def get_trends(
    request: Request,
    category: str = Path(..., description="트렌드 카테고리 (Registered trend category)"),
    limit: int = Query(20, ge=1, le=50, description="키워드 개수 상한 (Max keywords)"),
    _: None = Depends(require_api_key),
):
    rid = get_request_id(request)
    redis_key_kw = "trends:%s:keywords" % (category,)
    integration_trace.inbound(
        request,
        op="trends",
        raw_category=category,
        limit_requested=limit,
    )
    _log.info("[%s] get_trends category=%s limit=%d -> Redis 조회", rid, category, limit)
    if category not in VALID_CATEGORIES:
        integration_trace.outbound_redis_hit(
            request, op="trends", redis_key=redis_key_kw, status="404_unknown_category")
        _log.info("[%s] get_trends category=%s -> 404 unknown", rid, category)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown category: {category}")

    try:
        keywords = await get_trend(category, limit)
        updated_at = await get_updated_at(category)
    except RedisError:
        integration_trace.outbound_redis_hit(
            request, op="trends", redis_key=redis_key_kw, status="503_redis_error")
        _log.warning("[%s] get_trends category=%s -> 503 Redis error", rid, category)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Cache unavailable")

    if not keywords:
        integration_trace.outbound_redis_hit(
            request, op="trends", redis_key=redis_key_kw, status="503_empty_zset")
        _log.warning("[%s] get_trends category=%s -> 503 empty", rid, category)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Trend data unavailable")

    ranked = [{"keyword": k, "score": int(s)} for k, s in keywords]
    sample_kw = [(r["keyword"][:28], r["score"]) for r in ranked[:8]]
    integration_trace.outbound_redis_hit(
        request,
        op="trends",
        redis_key=redis_key_kw,
        status="200",
        updated_at=updated_at,
        keyword_rows_returned=len(ranked),
        sample_keywords_scores=sample_kw,
    )
    _log.info("[%s] get_trends category=%s -> keywords=%d updated_at=%s", rid, category, len(keywords),
              updated_at)
    return {
        "category": category,
        "updated_at": updated_at,
        "keywords": ranked,
    }
