"""시설 검색 — 이름(pg_trgm) + 태그 + 지역 + (옵션) 반경. 기존 /facilities 와 분리."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.core.auth import require_api_key
from app.platform.core.database import get_db
from app.serving.recommender.facilities import (
    CONTEXT_TO_FACILITY_TYPE,
    normalize_context,
)

router = APIRouter(prefix="/facilities", tags=["검색 (Search)"])


_VALID_SORTS = {"distance", "trend", "name"}


@router.get(
    "/search",
    summary="시설 검색 (Search facilities)",
    description=(
        "이름(pg_trgm) + 태그 + 지역 + (옵션) 반경. "
        "정렬: distance(반경 필요) / trend(태그·이름이 최신 트렌드 스냅샷 키워드와 매칭) / name. "
        "cursor 페이지네이션은 sort=name 에서만 안정적. distance/trend 정렬은 단일 페이지로 사용하세요."
    ),
)
async def search_facilities(
    q: Optional[str] = Query(None, min_length=1, max_length=100, description="이름 검색어 (pg_trgm 유사도)"),
    context: Optional[str] = Query(None, description="컨텍스트 (grooming|hospital|supplies 등)"),
    tags: Optional[str] = Query(None, description="콤마 구분 태그 — 하나라도 매칭되면 OK"),
    region_city: Optional[str] = Query(None, description="시·도"),
    region_district: Optional[str] = Query(None, description="시·군·구"),
    lat: Optional[float] = Query(None, description="기준 위도 (반경 필터·distance 정렬 시 필요)"),
    lng: Optional[float] = Query(None, description="기준 경도"),
    radius_km: Optional[float] = Query(None, ge=0.1, le=50.0, description="반경 km"),
    sort: str = Query("name", description="정렬: distance|trend|name (기본 name)"),
    cursor: int = Query(0, ge=0, description="이전 응답 next_cursor (sort=name 에서만 의미 있음)"),
    limit: int = Query(20, ge=1, le=50, description="페이지 크기"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    if sort not in _VALID_SORTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort: {sort}. Valid: {sorted(_VALID_SORTS)}",
        )

    if sort == "distance" and (lat is None or lng is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort=distance requires lat & lng",
        )

    ftype: Optional[str] = None
    if context:
        ftype = CONTEXT_TO_FACILITY_TYPE.get(normalize_context(context))

    tag_list: list[str] = []
    if tags:
        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]

    params: dict[str, object] = {"limit": limit + 1}
    where: list[str] = ["f.status = '영업'"]

    if sort == "name" and cursor:
        where.append("f.id > :cursor")
        params["cursor"] = cursor
    if ftype:
        where.append("f.type = :ftype")
        params["ftype"] = ftype
    if region_city:
        where.append("f.region_city = :region_city")
        params["region_city"] = region_city
    if region_district:
        where.append("f.region_district = :region_district")
        params["region_district"] = region_district
    if q:
        where.append("similarity(f.name, :q) > 0.1")
        params["q"] = q
    if tag_list:
        where.append(
            "EXISTS (SELECT 1 FROM facility_tags ft "
            "WHERE ft.facility_id = f.id AND lower(ft.tag) = ANY(:tag_list))"
        )
        params["tag_list"] = tag_list

    if lat is not None and lng is not None:
        distance_expr = (
            "6371000 * acos(LEAST(1.0, "
            "cos(radians(:lat)) * cos(radians(f.lat)) * "
            "cos(radians(f.lng) - radians(:lng)) + "
            "sin(radians(:lat)) * sin(radians(f.lat))))"
        )
        params["lat"] = lat
        params["lng"] = lng
    else:
        distance_expr = "NULL::float"

    if radius_km is not None and lat is not None and lng is not None:
        where.append("f.lat IS NOT NULL")
        params["radius_m"] = radius_km * 1000

    trend_score_expr = (
        "COALESCE((SELECT SUM(ts.score)::bigint FROM trend_snapshots ts "
        "WHERE ts.snapshot_date = (SELECT MAX(snapshot_date) FROM trend_snapshots) "
        "AND (position(lower(ts.keyword) in lower(f.name)) > 0 "
        "OR EXISTS (SELECT 1 FROM facility_tags ft2 "
        "WHERE ft2.facility_id = f.id AND lower(ft2.tag) = lower(ts.keyword)))), 0)"
    )

    if sort == "distance":
        order_clause = "distance_m ASC NULLS LAST, id ASC"
    elif sort == "name":
        order_clause = "name ASC, id ASC"
    else:
        order_clause = "trend_score DESC, id ASC"

    inner_sql = f"""
        SELECT
            f.id, f.source_id, f.name, f.type, f.status,
            f.address, f.region_city, f.region_district,
            f.phone, f.lat, f.lng,
            {distance_expr} AS distance_m,
            {trend_score_expr} AS trend_score
        FROM pet_facilities f
        WHERE {' AND '.join(where)}
    """

    if "radius_m" in params:
        sql = f"""
        SELECT * FROM ({inner_sql}) s
        WHERE distance_m <= :radius_m
        ORDER BY {order_clause}
        LIMIT :limit
        """
    else:
        sql = f"SELECT * FROM ({inner_sql}) s ORDER BY {order_clause} LIMIT :limit"

    result = await db.execute(text(sql), params)
    rows = result.mappings().all()

    has_next = len(rows) > limit
    rows = list(rows[:limit])

    items = [
        {
            "id": r["id"],
            "source_id": r["source_id"],
            "name": r["name"],
            "type": r["type"],
            "status": r["status"],
            "address": r["address"],
            "region_city": r["region_city"],
            "region_district": r["region_district"],
            "phone": r["phone"],
            "lat": r["lat"],
            "lng": r["lng"],
            "distance_m": int(r["distance_m"]) if r["distance_m"] is not None else None,
            "trend_score": int(r["trend_score"]) if r["trend_score"] is not None else 0,
        }
        for r in rows
    ]

    # cursor 는 sort=name 에서만 안정적. 다른 정렬은 has_next=False 로 강제.
    next_cursor: Optional[int] = None
    if sort == "name" and has_next and items:
        next_cursor = items[-1]["id"]
    if sort != "name":
        has_next = False

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_next": has_next,
        "sort": sort,
    }
