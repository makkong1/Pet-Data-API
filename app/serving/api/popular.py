import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from redis.exceptions import RedisError

from app.platform.cache.redis import get_redis
from app.platform.core.auth import require_api_key
from app.platform.observability import get_request_id
from app.platform.schemas.popular import PopularEntry
from app.platform import integration_trace

router = APIRouter(prefix="/popular", tags=["인기 (Popular)"])
_log = logging.getLogger(__name__)

_VALID_CONTEXTS = frozenset({
    "grooming",
    "hospital",
    "supplies",
    "pharmacy",
    "cafe",
    "pension",
    "restaurant",
    "boarding",
    "hotel",
})
_CONTEXT_ALIASES = {"snack": "supplies", "food": "supplies", "clothes": "supplies"}


@router.get(
    "/{context}",
    summary="컨텍스트별 인기 상호 (Popular businesses by context)",
    description="Naver 블로그 언급 기반 인기 상호 목록 (최대 20개). Redis `popular:{context}` 에서 조회.",
    response_model=List[PopularEntry],
)
async def get_popular(
    request: Request,
    context: str = Path(
        ...,
        description=(
            "grooming | hospital | supplies | pharmacy | cafe | "
            "pension | restaurant | boarding | hotel "
            "(snack/food/clothes → supplies)"
        ),
    ),
    limit: int = Query(20, ge=1, le=20, description="반환 상한"),
    _: None = Depends(require_api_key),
):
    rid = get_request_id(request)
    integration_trace.inbound(
        request,
        op="popular",
        raw_context=context,
        limit_requested=limit,
    )
    normalized = _CONTEXT_ALIASES.get(context, context)
    if normalized not in _VALID_CONTEXTS:
        integration_trace.outbound_redis_hit(
            request, op="popular", redis_key="-", status="404_unknown_context", normalized=normalized)
        _log.info("[%s] get_popular context=%s -> 404 unknown", rid, context)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown context: {context}",
        )

    key = f"popular:{normalized}"
    try:
        r = get_redis()
        raw = await r.get(key)
    except RedisError as e:
        integration_trace.outbound_redis_hit(
            request, op="popular", redis_key=key, status="503_redis_error")
        _log.warning("[%s] get_popular context=%s -> 503 Redis error %s", rid, normalized, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="popular data unavailable",
        ) from e

    if raw is None:
        integration_trace.outbound_redis_hit(
            request, op="popular", redis_key=key, status="503_missing_key")
        _log.warning("[%s] get_popular context=%s -> 503 no data", rid, normalized)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="popular data unavailable",
        )

    data: list = json.loads(raw)
    slice_ = data[:limit]
    sample = [str(x.get("name", "?"))[:32] for x in slice_[:8]]
    integration_trace.outbound_redis_hit(
        request,
        op="popular",
        redis_key=key,
        status="200",
        raw_context=context,
        normalized_context=normalized,
        redis_json_len=len(raw),
        in_cache=len(data),
        returning=len(slice_),
        sample_names=sample,
    )
    _log.info("[%s] get_popular context=%s -> count=%d limit=%d", rid, normalized, len(data), limit)
    return slice_
