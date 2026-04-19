from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_api_key
from app.schemas.stats import RegionStatResponse, TrendResponse

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/region", response_model=List[RegionStatResponse])
async def region_stats(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    result = await db.execute(
        text("SELECT region, date, total_count, adopted_count, euthanized_count FROM mv_region_stats ORDER BY date DESC, region")
    )
    return [RegionStatResponse(**dict(r)) for r in result.mappings()]


@router.get("/trend", response_model=List[TrendResponse])
async def trend_stats(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    result = await db.execute(
        text("""
            SELECT
                region,
                EXTRACT(YEAR FROM date)::int  AS year,
                EXTRACT(MONTH FROM date)::int AS month,
                SUM(total_count)::int         AS total_count,
                SUM(adopted_count)::int       AS adopted_count,
                SUM(euthanized_count)::int    AS euthanized_count
            FROM mv_region_stats
            WHERE EXTRACT(YEAR FROM date) = :year
              AND EXTRACT(MONTH FROM date) = :month
            GROUP BY region, year, month
            ORDER BY region
        """),
        {"year": year, "month": month},
    )
    return [TrendResponse(**dict(r)) for r in result.mappings()]
