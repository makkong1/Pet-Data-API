from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.facility import PetFacility
from app.schemas.facility import FacilityListResponse, FacilityResponse, FacilityDetailResponse

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=FacilityListResponse)
async def list_facilities(
    cursor: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    region_city: Optional[str] = None,
    region_district: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
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
    stmt = stmt.order_by(PetFacility.id).limit(limit + 1)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    has_next = len(items) > limit
    items = items[:limit]
    next_cursor = items[-1].id if has_next and items else None
    return FacilityListResponse(items=items, next_cursor=next_cursor, has_next=has_next)


@router.get("/{facility_id}", response_model=FacilityDetailResponse)
async def get_facility(
    facility_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    result = await db.execute(
        select(PetFacility).where(PetFacility.id == facility_id)
    )
    facility = result.scalar_one_or_none()
    if not facility:
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
