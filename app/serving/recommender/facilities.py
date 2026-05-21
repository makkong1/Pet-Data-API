from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CONTEXT_TO_FACILITY_TYPE: dict[str, Optional[str]] = {
    "grooming": "BUSINESS",
    "hospital": "HOSPITAL",
    "supplies": "BUSINESS",
    "pharmacy": "BUSINESS",
    "cafe": "BUSINESS",
    "pension": "BUSINESS",
    "restaurant": "BUSINESS",
    "boarding": "BUSINESS",
    "hotel": "BUSINESS",
}

LEGACY_CONTEXT_ALIASES: dict[str, str] = {
    "snack": "supplies",
    "food": "supplies",
    "clothes": "supplies",
}

VALID_CONTEXTS = set(CONTEXT_TO_FACILITY_TYPE.keys()) | set(LEGACY_CONTEXT_ALIASES.keys())

# context가 특정 category로 매핑되면 category 필터 추가. None이면 type 필터만 사용.
CONTEXT_TO_CATEGORY: dict[str, Optional[str]] = {
    "grooming":   "grooming",
    "hospital":   "hospital",
    "pharmacy":   "pharmacy",
    "supplies":   None,
    "cafe":       None,
    "pension":    None,
    "restaurant": None,
    "boarding":   None,
    "hotel":      None,
}

_HAVERSINE_SQL = """
WITH distances AS (
    SELECT
        id,
        source_id,
        name,
        address,
        lat,
        lng,
        6371000 * acos(
            LEAST(1.0,
                cos(radians(:lat)) * cos(radians(lat)) *
                cos(radians(lng) - radians(:lng)) +
                sin(radians(:lat)) * sin(radians(lat))
            )
        ) AS distance_m
    FROM pet_facilities
    WHERE lat IS NOT NULL
      AND type = :ftype
)
SELECT id, source_id, name, address, lat, lng, distance_m
FROM distances
WHERE distance_m <= :radius_m
ORDER BY distance_m
LIMIT :top_n
"""

_HAVERSINE_SQL_WITH_CATEGORY = """
WITH distances AS (
    SELECT
        id,
        source_id,
        name,
        address,
        lat,
        lng,
        6371000 * acos(
            LEAST(1.0,
                cos(radians(:lat)) * cos(radians(lat)) *
                cos(radians(lng) - radians(:lng)) +
                sin(radians(:lat)) * sin(radians(lat))
            )
        ) AS distance_m
    FROM pet_facilities
    WHERE lat IS NOT NULL
      AND type = :ftype
      AND category = :category
)
SELECT id, source_id, name, address, lat, lng, distance_m
FROM distances
WHERE distance_m <= :radius_m
ORDER BY distance_m
LIMIT :top_n
"""


def normalize_context(context: str) -> str:
    return LEGACY_CONTEXT_ALIASES.get(context, context)


async def get_nearby_facilities(
    db: AsyncSession,
    lat: float,
    lng: float,
    context: str,
    radius_km: float,
    top_n: int,
) -> list[dict]:
    normalized_context = normalize_context(context)
    ftype = CONTEXT_TO_FACILITY_TYPE.get(normalized_context)
    if ftype is None:
        return []

    category = CONTEXT_TO_CATEGORY.get(normalized_context)
    if category:
        sql = _HAVERSINE_SQL_WITH_CATEGORY
        params = {"lat": lat, "lng": lng, "ftype": ftype, "category": category,
                  "radius_m": radius_km * 1000, "top_n": top_n}
    else:
        sql = _HAVERSINE_SQL
        params = {"lat": lat, "lng": lng, "ftype": ftype,
                  "radius_m": radius_km * 1000, "top_n": top_n}

    result = await db.execute(text(sql), params)
    rows = result.mappings().all()
    return [
        {
            "facility_id": r.get("id"),
            "source_id": r["source_id"],
            "name": r["name"],
            "distance_m": int(r["distance_m"]),
            "address": r["address"],
            "lat": r.get("lat"),
            "lng": r.get("lng"),
        }
        for r in rows
    ]
