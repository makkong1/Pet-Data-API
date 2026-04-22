from typing import Optional
import httpx
from app.core.config import settings

KAKAO_GEOCODE_URL = "https://dapi.kakao.com/v2/local/search/address.json"


async def geocode_address(address: str) -> Optional[tuple[float, float]]:
    """주소 → (lat, lng). 실패 시 None 반환."""
    if not settings.KAKAO_REST_API_KEY or not address.strip():
        return None
    headers = {"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"}
    params = {"query": address}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(KAKAO_GEOCODE_URL, headers=headers, params=params)
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            if docs:
                return float(docs[0]["y"]), float(docs[0]["x"])  # (lat, lng)
    except Exception:
        pass
    return None
