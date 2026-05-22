import logging
from typing import List
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.platform.core.database import get_db
from app.platform.core.auth import require_api_key
from app.platform.schemas.stats import SummaryResponse
from app.platform.observability import get_request_id

router = APIRouter(prefix="/stats", tags=["통계 (Stats)"])
_log = logging.getLogger(__name__)


@router.get(
    "/summary",
    response_model=List[SummaryResponse],
    summary="요약 통계 (Summary stats)",
    description="영업 중 시설만 지역·유형별 집계. (Open facilities only, grouped by region and type.)",
)
async def summary_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    rid = get_request_id(request)
    _log.info("[%s] stats_summary -> 영업 중 시설 지역·유형별 집계", rid)
    result = await db.execute(
        text("""
            SELECT type, region_city, region_district, COUNT(*)::int AS count
            FROM pet_facilities
            WHERE status = '영업'
            GROUP BY type, region_city, region_district
            ORDER BY region_city, region_district, type
        """)
    )
    rows = [SummaryResponse(**dict(r)) for r in result.mappings()]
    _log.info("[%s] stats_summary -> rows=%d", rid, len(rows))
    return rows
