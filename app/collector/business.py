from typing import Optional
from app.collector.client import fetch_public_api
from app.core.config import settings

BUSINESS_API_URL = "http://apis.data.go.kr/1543061/petShopSrvc/petShopSrvc"


async def fetch_businesses(page: int = 1, num_of_rows: int = 1000) -> dict:
    params = {
        "serviceKey": settings.PUBLIC_DATA_API_KEY,
        "pageNo": page,
        "numOfRows": num_of_rows,
        "_type": "json",
    }
    return await fetch_public_api(BUSINESS_API_URL, params)


def parse_business_item(raw: dict) -> dict:
    return {
        "source_id": raw.get("mgtNo", ""),
        "type": "BUSINESS",
        "name": raw.get("bsnNm", ""),
        "status": raw.get("bsnStts", ""),
        "address": raw.get("rdnAdr", ""),
        "region_city": raw.get("ctpvNm", ""),
        "region_district": raw.get("signguNm", ""),
        "phone": raw.get("telNo") or None,
        "business_type": raw.get("uptaeNm", ""),
        "registration_no": raw.get("mgtNo") or None,
    }


def extract_businesses(response: dict) -> list:
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_business_item(item) for item in items]
    except (KeyError, TypeError):
        return []
