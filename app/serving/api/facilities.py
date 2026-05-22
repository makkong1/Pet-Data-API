import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, Path, Query, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.platform.core.database import get_db
from app.platform.core.auth import require_api_key
from app.platform.models.facility import PetFacility
from app.platform.schemas.facility import FacilityListResponse, FacilityResponse, FacilityDetailResponse
from app.platform.observability import get_request_id

router = APIRouter(prefix="/facilities", tags=["시설 (Facilities)"])
_log = logging.getLogger(__name__)


@router.get(
    "",
    response_model=FacilityListResponse,
    summary="시설 목록 (List facilities)",
    description="커서 기반 페이지네이션. (Keyset pagination by facility id.)",
)
async def list_facilities(
    request: Request,
    cursor: int = Query(0, ge=0, description="이전 응답 next_cursor (Previous next_cursor)"),
    limit: int = Query(20, ge=1, le=100, description="페이지 크기 (Page size)"),
    type: Optional[str] = Query(None, description="시설 유형 필터 (Facility type filter)"),
    region_city: Optional[str] = Query(None, description="시·도 (City)"),
    region_district: Optional[str] = Query(None, description="시·군·구 (District)"),
    status_filter: Optional[str] = Query(None, alias="status", description="영업 상태 등 (Status, e.g. 영업)"),
    category: Optional[str] = Query(None, description="카테고리 필터 (Category, e.g. grooming | hospital | pharmacy)"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    rid = get_request_id(request)
    _log.info(
        "[%s] list_facilities cursor=%d limit=%d type=%s city=%s district=%s status=%s category=%s",
        rid, cursor, limit, type, region_city, region_district, status_filter, category,
    )
    stmt = select(PetFacility)
    if cursor:
        stmt = stmt.where(PetFacility.id > cursor)
    if type:
        stmt = stmt.where(PetFacility.type == type)
    if region_city:
        stmt = stmt.where(PetFacility.region_city == region_city)
    if region_district:
        stmt = stmt.where(PetFacility.region_district == region_district)
    if status_filter:
        stmt = stmt.where(PetFacility.status == status_filter)
    if category:
        stmt = stmt.where(PetFacility.category == category)
    stmt = stmt.order_by(PetFacility.id).limit(limit + 1)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    has_next = len(items) > limit
    items = items[:limit]
    next_cursor = items[-1].id if has_next and items else None
    _log.info("[%s] list_facilities -> items=%d has_next=%s next_cursor=%s", rid, len(items), has_next, next_cursor)
    return FacilityListResponse(items=items, next_cursor=next_cursor, has_next=has_next)


@router.get(
    "/{facility_id}",
    response_model=FacilityDetailResponse,
    summary="시설 상세 (Get facility)",
    description="유형별 확장 상세(영업장/병원). (Type-specific detail fields.)",
)
async def get_facility(
    request: Request,
    facility_id: int = Path(..., description="시설 내부 ID (Internal facility id)"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    rid = get_request_id(request)
    _log.info("[%s] get_facility facility_id=%d", rid, facility_id)
    result = await db.execute(
        select(PetFacility).where(PetFacility.id == facility_id)
    )
    facility = result.scalar_one_or_none()
    if not facility:
        _log.info("[%s] get_facility facility_id=%d -> 404 not found", rid, facility_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found")

    details: dict = {}
    if facility.type == "BUSINESS":
        r = await db.execute(
            text("SELECT business_type, registration_no FROM business_details WHERE facility_id = :fid"),
            {"fid": facility_id},
        )
        row = r.mappings().first()
        if row:
            details = dict(row)
    elif facility.type == "HOSPITAL":
        r = await db.execute(
            text("SELECT license_no, specialty FROM hospital_details WHERE facility_id = :fid"),
            {"fid": facility_id},
        )
        row = r.mappings().first()
        if row:
            details = dict(row)

    _log.info(
        "[%s] get_facility facility_id=%d -> name=%s type=%s status=%s",
        rid, facility_id, facility.name, facility.type, facility.status,
    )
    return FacilityDetailResponse(
        id=facility.id,
        source_id=facility.source_id,
        type=facility.type,
        name=facility.name,
        status=facility.status,
        address=facility.address,
        region_city=facility.region_city,
        region_district=facility.region_district,
        phone=facility.phone,
        collected_at=facility.collected_at,
        details=details,
    )
