from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.platform.core.database import get_db
from app.platform.core.auth import require_api_key
from app.platform.schemas.stats import SummaryResponse

router = APIRouter(prefix="/stats", tags=["통계 (Stats)"])


@router.get(
    "/summary",
    response_model=List[SummaryResponse],
    summary="요약 통계 (Summary stats)",
    description="영업 중 시설만 지역·유형별 집계. (Open facilities only, grouped by region and type.)",
)
async def summary_stats(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    result = await db.execute(
        text("""
            SELECT type, region_city, region_district, COUNT(*)::int AS count
            FROM pet_facilities
            WHERE status = '영업'
            GROUP BY type, region_city, region_district
            ORDER BY region_city, region_district, type
        """)
    )
    return [SummaryResponse(**dict(r)) for r in result.mappings()]
