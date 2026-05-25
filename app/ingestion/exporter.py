"""
popular 수집 결과를 LocationImportDto dict로 변환하고 일괄 수집하는 모듈.
Redis 의존 없음 — CLI / cron 전용.
"""
import logging
from typing import Optional

from app.ingestion.blog import collect_popular_for_context
from app.ingestion.local_discovery import collect_popular_local_discovery
from app.ingestion.location import enrich_with_location

_log = logging.getLogger(__name__)

POPULAR_CONTEXTS: list[str] = [
    "grooming", "hospital", "supplies", "pharmacy",
    "cafe", "pension", "restaurant", "boarding", "hotel",
]
_LOCAL_DISCOVERY_CONTEXTS: frozenset[str] = frozenset({"boarding", "hotel"})


def _coord(val: Optional[str]) -> Optional[float]:
    """Naver mapx/mapy 문자열(위도·경도 × 10^7)을 소수점 도(°) 좌표로 변환."""
    if not val:
        return None
    try:
        v = float(val)
        return v / 1e7 if v != 0 else None
    except (ValueError, TypeError):
        return None


def parse_address_parts(address: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """주소 문자열의 첫 두 토큰을 sido, sigungu로 반환."""
    if not address:
        return None, None
    parts = address.split()
    return (parts[0] if parts else None), (parts[1] if len(parts) > 1 else None)


def popular_dict_to_dto(d: dict, category: str) -> dict:
    """수집 결과 dict → LocationImportDto dict 변환."""
    address = d.get("road_address") or d.get("address")
    sido, sigungu = parse_address_parts(address)
    return {
        "name":     d["name"],
        "category": category,
        "address":  address,
        "sido":     sido,
        "sigungu":  sigungu,
        "lat":      _coord(d.get("map_y")),
        "lng":      _coord(d.get("map_x")),
        "phone":    d.get("telephone"),
        "status":   "운영중",
    }


async def collect_popular_for_cli(contexts: list[str]) -> list[dict]:
    """
    popular 수집 파이프라인 실행 — Redis 저장 없이 LocationImportDto list 반환.
    runner.run_popular_collection()과 동일 로직에서 save_popular() 호출만 제거.
    """
    result: list[dict] = []
    for context in contexts:
        try:
            if context in _LOCAL_DISCOVERY_CONTEXTS:
                entries = await collect_popular_local_discovery(context)
            else:
                entries = await collect_popular_for_context(context)
                if entries:
                    entries = await enrich_with_location(entries, context)
            dtos = [popular_dict_to_dto(e, context) for e in entries if e.get("name")]
            _log.info("exporter context=%s count=%d", context, len(dtos))
            result.extend(dtos)
        except Exception as e:
            _log.error("exporter failed context=%s err=%s", context, e)
    return result
