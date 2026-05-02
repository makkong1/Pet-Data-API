import logging
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_api_key
from app.schemas.recommend import RecommendRequest, RecommendResponse, FacilityItem, TrendKeyword
from app.recommender.facilities import get_nearby_facilities, VALID_CONTEXTS, normalize_context
from app.recommender.builder import build_prompt
from app.recommender.llm import generate_recommendation
from app.cache.redis import get_trend

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
    description="근처 시설·트렌드·LLM 추천 문구. (Nearby facilities, trends, optional LLM text.)",
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
    facilities_raw = await get_nearby_facilities(
        db, req.lat, req.lng, normalized_context, req.radius_km, req.top_n
    )

    trends_raw = await _load_trends_for_context(req.context, 10)

    trends = [TrendKeyword(keyword=k, score=int(s)) for k, s in trends_raw]
    facilities = [FacilityItem(**f) for f in facilities_raw]

    if not facilities_raw and not trends_raw:
        recommendation = None
    else:
        pet_dict = req.pet.model_dump() if req.pet else None
        prompt = build_prompt(normalized_context, facilities_raw, [t.model_dump() for t in trends], pet_dict)
        recommendation = await generate_recommendation(prompt)

    response = RecommendResponse(
        context=req.context,
        facilities=facilities,
        trends=trends,
        recommendation=recommendation,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    _log.info("recommend response: %s", response.model_dump_json())
    return response
