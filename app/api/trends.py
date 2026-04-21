from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.cache.redis import get_trend, get_updated_at
from app.core.auth import require_api_key
from app.collector.naver import CATEGORY_KEYWORDS

router = APIRouter(prefix="/trends", tags=["trends"])

VALID_CATEGORIES = set(CATEGORY_KEYWORDS.keys())


@router.get("/{category}")
async def get_trends(
    category: str,
    limit: int = Query(20, ge=1, le=50),
    _: None = Depends(require_api_key),
):
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown category: {category}")

    keywords = await get_trend(category, limit)
    if not keywords:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Trend data unavailable")

    updated_at = await get_updated_at(category)
    return {
        "category": category,
        "updated_at": updated_at,
        "keywords": [{"keyword": k, "score": int(s)} for k, s in keywords],
    }
