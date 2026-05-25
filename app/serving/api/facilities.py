import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.platform.cache.redis import get_redis
from app.platform.core.auth import require_api_key

router = APIRouter(prefix="/facilities", tags=["시설 (Facilities)"])
_log = logging.getLogger(__name__)

_POPULAR_CONTEXTS = [
    "grooming", "hospital", "supplies", "pharmacy",
    "cafe", "pension", "restaurant", "boarding", "hotel",
]


class FacilityItem(BaseModel):
    name: str
    category: str
    address: Optional[str] = None
    region_city: Optional[str] = None
    region_district: Optional[str] = None
    phone: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    status: Optional[str] = None


class FacilityPageResponse(BaseModel):
    items: List[FacilityItem]
    next_cursor: Optional[int] = None
    has_next: bool


def _parse_region(address: Optional[str]):
    """'서울특별시 강남구 ...' → ('서울', '강남구')"""
    if not address:
        return None, None
    parts = address.split()
    if not parts:
        return None, None
    city = parts[0].replace("특별시", "").replace("광역시", "").replace("시", "")
    district = parts[1] if len(parts) > 1 else None
    return city or None, district


def _map_xy_to_latlon(map_x: Optional[str], map_y: Optional[str]):
    """Naver local map_x/map_y (× 10,000,000 정수 문자열) → float lat/lng"""
    try:
        lat = int(map_y) / 10_000_000.0 if map_y else None
        lng = int(map_x) / 10_000_000.0 if map_x else None
        return lat, lng
    except (ValueError, TypeError):
        return None, None


async def _load_all_facilities() -> List[FacilityItem]:
    """Redis popular:* 전체 키 스캔 → address 있는 항목만 FacilityItem으로 변환."""
    r = get_redis()
    items: List[FacilityItem] = []
    seen: set = set()

    for context in _POPULAR_CONTEXTS:
        key = f"popular:{context}"
        try:
            raw = await r.get(key)
        except Exception as exc:
            _log.warning("facilities: Redis get failed key=%s err=%s", key, exc)
            continue
        if not raw:
            continue

        try:
            entries = json.loads(raw)
        except Exception:
            continue

        for entry in entries:
            name = entry.get("name", "")
            if not name:
                continue
            address = entry.get("road_address") or entry.get("address")
            if not address:
                continue

            dedup_key = (name, address)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            lat, lng = _map_xy_to_latlon(entry.get("map_x"), entry.get("map_y"))
            city, district = _parse_region(address)

            items.append(FacilityItem(
                name=name,
                category=context,
                address=address,
                region_city=city,
                region_district=district,
                phone=entry.get("telephone"),
                lat=lat,
                lng=lng,
                status=None,
            ))

    return items


@router.get(
    "",
    summary="시설 목록 (cursor 기반 페이징)",
    description=(
        "Petory FacilitySyncService가 호출하는 시설 목록 API. "
        "Redis popular 캐시 기반. address 없는 항목은 제외."
    ),
    response_model=FacilityPageResponse,
)
async def list_facilities(
    request: Request,
    cursor: int = Query(0, ge=0, description="페이징 커서 (offset)"),
    limit: int = Query(100, ge=1, le=500, description="페이지 크기"),
    _: None = Depends(require_api_key),
):
    all_items = await _load_all_facilities()
    total = len(all_items)
    page = all_items[cursor: cursor + limit]
    next_cursor = cursor + limit if cursor + limit < total else None

    _log.info(
        "GET /facilities cursor=%d limit=%d total=%d returning=%d",
        cursor, limit, total, len(page),
    )

    return FacilityPageResponse(
        items=page,
        next_cursor=next_cursor,
        has_next=next_cursor is not None,
    )
