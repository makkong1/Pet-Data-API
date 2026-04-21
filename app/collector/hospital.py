from urllib.parse import quote_plus
from app.core.config import settings
from app.collector.client import fetch_public_api

HOSPITAL_API_URL = "https://apis.data.go.kr/1741000/animal_hospitals/info"


def _parse_region(addr: str):
    parts = addr.split()
    city = parts[0] if len(parts) > 0 else ""
    district = parts[1] if len(parts) > 1 else ""
    return city, district


async def fetch_hospitals(page: int = 1, num_of_rows: int = 1000) -> dict:
    key = quote_plus(settings.HOSPITAL_API_KEY)
    url = f"{HOSPITAL_API_URL}?serviceKey={key}&pageNo={page}&numOfRows={num_of_rows}"
    return await fetch_public_api(url)


def parse_hospital_item(raw: dict) -> dict:
    addr = raw.get("ROAD_NM_ADDR") or raw.get("LOTNO_ADDR", "")
    region_city, region_district = _parse_region(addr)
    return {
        "source_id": raw.get("MNG_NO", ""),
        "type": "HOSPITAL",
        "name": raw.get("BPLC_NM", ""),
        "status": raw.get("SALS_STTS_NM", ""),
        "address": addr,
        "region_city": region_city,
        "region_district": region_district,
        "phone": raw.get("TELNO") or None,
        "license_no": raw.get("LCPMT_YMD") or None,
        "specialty": raw.get("DTL_TASK_SE_NM") or None,
    }


def extract_hospitals(response: dict) -> list:
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_hospital_item(item) for item in items]
    except (KeyError, TypeError):
        return []
