import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession
from app.platform.cache.redis import get_trend, get_updated_at
from app.platform.core.auth import require_api_key
from app.platform.core.database import get_db
from app.ingestion.naver import CATEGORY_KEYWORDS
from app.ingestion.trend_history import fetch_trend_timeseries
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
    _log.info("[%s] get_trends category=%s limit=%d -> Redis 조회", rid, category, limit)
    if category not in VALID_CATEGORIES:
        _log.info("[%s] get_trends category=%s -> 404 unknown", rid, category)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown category: {category}")

    try:
        keywords = await get_trend(category, limit)
        updated_at = await get_updated_at(category)
    except RedisError:
        _log.warning("[%s] get_trends category=%s -> 503 Redis error", rid, category)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Cache unavailable")

    if not keywords:
        _log.warning("[%s] get_trends category=%s -> 503 empty", rid, category)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Trend data unavailable")
    _log.info("[%s] get_trends category=%s -> keywords=%d updated_at=%s", rid, category, len(keywords), updated_at)
    return {
        "category": category,
        "updated_at": updated_at,
        "keywords": [{"keyword": k, "score": int(s)} for k, s in keywords],
    }


@router.get(
    "/{category}/timeseries",
    summary="카테고리별 트렌드 시계열 (Trend time-series)",
    description="Postgres `trend_snapshots` 기반 최근 N일치 키워드 점수 추이. "
    "Redis 가 핫 캐시, 이쪽은 시계열 분석·증감률 계산용.",
)
async def get_trend_timeseries(
    request: Request,
    category: str = Path(..., description="트렌드 카테고리 (Registered trend category)"),
    days: int = Query(14, ge=1, le=90, description="최근 며칠치 (Lookback days)"),
    top_keywords: int = Query(10, ge=1, le=30, description="상위 키워드 수 (Top N by latest score)"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    rid = get_request_id(request)
    _log.info("[%s] trend_timeseries category=%s days=%d top_keywords=%d -> DB 조회", rid, category, days, top_keywords)
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown category: {category}")

    points = await fetch_trend_timeseries(db, category, days=days, top_keywords=top_keywords)
    _log.info("[%s] trend_timeseries category=%s -> points=%d", rid, category, len(points))
    return {
        "category": category,
        "days": days,
        "top_keywords": top_keywords,
        "points": points,
    }
