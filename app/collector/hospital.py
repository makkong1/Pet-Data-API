from urllib.parse import quote_plus
from app.core.config import settings
from app.collector.client import fetch_public_api

HOSPITAL_API_URL = "https://apis.data.go.kr/1741000/animal_hospitals/info"
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


def _extract_total_count(response: dict):
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
        raise RuntimeError(f"Hospital API error ({result_code}): {result_msg}")


async def fetch_hospitals(page: int = 1, num_of_rows: int = 1000) -> dict:
    key = quote_plus(settings.HOSPITAL_API_KEY)
    url = f"{HOSPITAL_API_URL}?serviceKey={key}&pageNo={page}&numOfRows={num_of_rows}"
    return await fetch_public_api(url)


async def fetch_all_hospitals(num_of_rows: int = 1000, max_pages: int = 200) -> list[dict]:
    page = 1
    all_items: list[dict] = []

    while page <= max_pages:
        response = await fetch_hospitals(page=page, num_of_rows=num_of_rows)
        items = extract_hospitals(response)
        all_items.extend(items)

        total_count = _extract_total_count(response)
        if total_count is not None and page * num_of_rows >= total_count:
            break
        if len(items) < num_of_rows:
            break
        page += 1

    return all_items


def parse_hospital_item(raw: dict) -> dict:
    addr = raw.get("ROAD_NM_ADDR") or raw.get("LOTNO_ADDR", "")
    region_city, region_district = _parse_region(addr)
    return {
        "source_id": raw.get("MNG_NO", ""),
        "type": "HOSPITAL",
        "name": raw.get("BPLC_NM", ""),
        "status": _normalize_status(raw.get("SALS_STTS_NM", "")),
        "address": addr,
        "region_city": region_city,
        "region_district": region_district,
        "phone": raw.get("TELNO") or None,
        "license_no": raw.get("LCPMT_YMD") or None,
        "specialty": raw.get("DTL_TASK_SE_NM") or None,
    }


def extract_hospitals(response: dict) -> list:
    _validate_response_or_raise(response)
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_hospital_item(item) for item in items]
    except (KeyError, TypeError):
        return []
