from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_api_key
from app.schemas.recommend import RecommendRequest, RecommendResponse, FacilityItem, TrendKeyword
from app.recommender.facilities import get_nearby_facilities, VALID_CONTEXTS
from app.recommender.builder import build_prompt
from app.recommender.llm import generate_recommendation
from app.cache.redis import get_trend

router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.post("", response_model=RecommendResponse)
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

    facilities_raw = await get_nearby_facilities(
        db, req.lat, req.lng, req.context, req.radius_km, req.top_n
    )

    try:
        trends_raw = await get_trend(req.context, 10)
    except Exception:
        trends_raw = []

    trends = [TrendKeyword(keyword=k, score=int(s)) for k, s in trends_raw]
    facilities = [FacilityItem(**f) for f in facilities_raw]

    pet_dict = req.pet.model_dump() if req.pet else None
    prompt = build_prompt(req.context, facilities_raw, [t.model_dump() for t in trends], pet_dict)
    recommendation = await generate_recommendation(prompt)

    return RecommendResponse(
        context=req.context,
        facilities=facilities,
        trends=trends,
        recommendation=recommendation,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
