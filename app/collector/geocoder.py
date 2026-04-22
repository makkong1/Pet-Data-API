from typing import Optional
import httpx
from app.core.config import settings

NAVER_GEOCODE_URL = "https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"


async def geocode_address(address: str) -> Optional[tuple[float, float]]:
    """주소 → (lat, lng). 실패 시 None 반환."""
    if not settings.NAVER_MAP_CLIENT_ID:
        return None
    headers = {
        "X-NCP-APIGW-API-KEY-ID": settings.NAVER_MAP_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": settings.NAVER_MAP_CLIENT_SECRET,
    }
    params = {"query": address}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(NAVER_GEOCODE_URL, headers=headers, params=params)
            resp.raise_for_status()
            addresses = resp.json().get("addresses", [])
            if addresses:
                return float(addresses[0]["y"]), float(addresses[0]["x"])  # (lat, lng)
    except Exception:
        pass
    return None
