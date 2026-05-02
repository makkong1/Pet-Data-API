from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CONTEXT_TO_FACILITY_TYPE: dict[str, Optional[str]] = {
    "grooming": "BUSINESS",
    "hospital": "HOSPITAL",
    "supplies": "BUSINESS",
}

LEGACY_CONTEXT_ALIASES: dict[str, str] = {
    "snack": "supplies",
    "food": "supplies",
    "clothes": "supplies",
}

VALID_CONTEXTS = set(CONTEXT_TO_FACILITY_TYPE.keys()) | set(LEGACY_CONTEXT_ALIASES.keys())

_HAVERSINE_SQL = """
WITH distances AS (
    SELECT
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
SELECT name, address, lat, lng, distance_m
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

    result = await db.execute(
        text(_HAVERSINE_SQL),
        {
            "lat": lat,
            "lng": lng,
            "ftype": ftype,
            "radius_m": radius_km * 1000,
            "top_n": top_n,
        },
    )
    rows = result.mappings().all()
    return [
        {
            "name": r["name"],
            "distance_m": int(r["distance_m"]),
            "address": r["address"],
            "lat": r.get("lat"),
            "lng": r.get("lng"),
        }
        for r in rows
    ]
