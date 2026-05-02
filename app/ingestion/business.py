from urllib.parse import quote_plus
from typing import Optional
from app.platform.core.config import settings
from app.ingestion.client import fetch_public_api

BUSINESS_API_URL = "https://apis.data.go.kr/1741000/pet_grooming/info"
SUCCESS_RESULT_CODE = "00"

def _parse_region(addr: str):
    parts = addr.split()
    city = parts[0] if len(parts) > 0 else ""
    district = parts[1] if len(parts) > 1 else ""
    return city, district

def _normalize_status(raw_status: str) -> str:
    status = (raw_status or "").strip()
    if not status:
        return "미상"
    if "영업" in status:
        return "영업"
    if "폐업" in status:
        return "폐업"
    return status

def _extract_total_count(response: dict) -> Optional[int]:
    try:
        total = response["response"]["body"]["totalCount"]
        return int(total)
    except (KeyError, TypeError, ValueError):
        return None

def _validate_response_or_raise(response: dict) -> None:
    header = response.get("response", {}).get("header", {})
    result_code = str(header.get("resultCode", SUCCESS_RESULT_CODE)).strip()
    if result_code and result_code != SUCCESS_RESULT_CODE:
        result_msg = header.get("resultMsg", "Unknown error")
        raise RuntimeError(f"Business API error ({result_code}): {result_msg}")

async def fetch_businesses(page: int = 1, num_of_rows: int = 1000) -> dict:
    key = quote_plus(settings.PUBLIC_DATA_API_KEY)
    url = f"{BUSINESS_API_URL}?serviceKey={key}&pageNo={page}&numOfRows={num_of_rows}"
    return await fetch_public_api(url)

async def fetch_all_businesses(num_of_rows: int = 1000, max_pages: int = 200) -> list[dict]:
    page = 1
    all_items: list[dict] = []

    while page <= max_pages:
        response = await fetch_businesses(page=page, num_of_rows=num_of_rows)
        items = extract_businesses(response)
        all_items.extend(items)

        total_count = _extract_total_count(response)
        if total_count is not None and page * num_of_rows >= total_count:
            break
        if len(items) < num_of_rows:
            break
        page += 1

    return all_items

def parse_business_item(raw: dict) -> dict:
    addr = raw.get("ROAD_NM_ADDR") or raw.get("LOTNO_ADDR", "")
    region_city, region_district = _parse_region(addr)
    return {
        "source_id": raw.get("MNG_NO", ""),
        "type": "BUSINESS",
        "name": raw.get("BPLC_NM", ""),
        "status": _normalize_status(raw.get("SALS_STTS_NM", "")),
        "address": addr,
        "region_city": region_city,
        "region_district": region_district,
        "phone": raw.get("TELNO") or None,
        "business_type": "동물미용업",
        "registration_no": raw.get("MNG_NO") or None,
    }

def extract_businesses(response: dict) -> list:
    _validate_response_or_raise(response)
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_business_item(item) for item in items]
    except (KeyError, TypeError):
        return []
