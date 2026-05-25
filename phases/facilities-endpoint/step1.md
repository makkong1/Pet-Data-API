# Step 1: GET /facilities 엔드포인트 구현

## 목표

Petory `FacilitySyncService`가 매일 01:00에 호출하는 `GET /facilities` 엔드포인트를 구현한다.
Redis `popular:{context}` 캐시를 스캔해서 cursor 기반으로 시설 목록을 반환한다.

## 배경

- Petory `FacilitySyncScheduler` (01:00 daily) → `PetDataApiClient.fetchAllFacilities()` → `GET /facilities` 호출
- 현재 404 반환 → FacilitySyncService graceful fallback → no-op
- 이 엔드포인트가 구현되면 Petory `locationservice` 테이블에 `dataSource = "PET_DATA_API"` 시설이 쌓인다

## Petory가 기대하는 계약

`PetDataApiClient.java:373–393` 기준:

```
GET /facilities?cursor={Long}&limit={int}

Response 200:
{
  "items": [
    {
      "name":            "해피독",
      "category":        "grooming",
      "address":         "서울시 강남구 역삼동 ...",
      "region_city":     "서울",
      "region_district": "강남구",
      "phone":           "02-xxx-xxxx",
      "lat":             37.4979,
      "lng":             127.0276,
      "status":          null
    }
  ],
  "next_cursor": 100,
  "has_next": true
}
```

`FacilitySyncService.isValid()` 조건: `name` 비면 skip, `address` 비면 skip, `status == "폐업"` 이면 skip.

## 변경 파일

### 1. `app/serving/api/facilities.py` (신규)

```python
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
    city = parts[0].replace("특별시", "").replace("광역시", "").replace("시", "") if parts else None
    district = parts[1] if len(parts) > 1 else None
    return city, district


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
    description="Petory FacilitySyncService가 호출하는 시설 목록 API. Redis popular 캐시 기반.",
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

    _log.info("GET /facilities cursor=%d limit=%d total=%d returning=%d",
              cursor, limit, total, len(page))

    return FacilityPageResponse(
        items=page,
        next_cursor=next_cursor,
        has_next=next_cursor is not None,
    )
```

### 2. `app/main.py` (수정)

라우터 임포트 + 등록 추가:

```python
from app.serving.api.facilities import router as facilities_router
# ...
app.include_router(facilities_router)
```

## AC (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate

# 서버 시작 후 수동 확인
curl -s -H "X-API-Key: $API_KEY" http://localhost:8000/facilities?cursor=0&limit=10 | python3 -m json.tool

# pytest (다음 step에서 작성)
pytest tests/test_facilities_api.py -v
```
