from urllib.parse import quote_plus
from app.core.config import settings
from app.collector.client import fetch_public_api

BUSINESS_API_URL = "https://apis.data.go.kr/1741000/pet_grooming/info"


def _parse_region(addr: str):
    parts = addr.split()
    city = parts[0] if len(parts) > 0 else ""
    district = parts[1] if len(parts) > 1 else ""
    return city, district


async def fetch_businesses(page: int = 1, num_of_rows: int = 1000) -> dict:
    key = quote_plus(settings.PUBLIC_DATA_API_KEY)
    url = f"{BUSINESS_API_URL}?serviceKey={key}&pageNo={page}&numOfRows={num_of_rows}"
    return await fetch_public_api(url)


def parse_business_item(raw: dict) -> dict:
    addr = raw.get("ROAD_NM_ADDR") or raw.get("LOTNO_ADDR", "")
    region_city, region_district = _parse_region(addr)
    return {
        "source_id": raw.get("MNG_NO", ""),
        "type": "BUSINESS",
        "name": raw.get("BPLC_NM", ""),
        "status": raw.get("SALS_STTS_NM", ""),
        "address": addr,
        "region_city": region_city,
        "region_district": region_district,
        "phone": raw.get("TELNO") or None,
        "business_type": "동물미용업",
        "registration_no": raw.get("MNG_NO") or None,
    }


def extract_businesses(response: dict) -> list:
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_business_item(item) for item in items]
    except (KeyError, TypeError):
        return []
