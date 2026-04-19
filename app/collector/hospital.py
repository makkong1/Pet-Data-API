from typing import Optional
from app.collector.client import fetch_public_api
from app.core.config import settings

HOSPITAL_API_URL = "http://apis.data.go.kr/B553077/api/open/sdsc2/storeListInUpjong"


async def fetch_hospitals(page: int = 1, num_of_rows: int = 1000) -> dict:
    params = {
        "serviceKey": settings.PUBLIC_DATA_API_KEY,
        "pageNo": page,
        "numOfRows": num_of_rows,
        "indsLclsCd": "Q",
        "indsMclsCd": "Q12",
        "_type": "json",
    }
    return await fetch_public_api(HOSPITAL_API_URL, params)


def parse_hospital_item(raw: dict) -> dict:
    return {
        "source_id": raw.get("mgtNo", ""),
        "type": "HOSPITAL",
        "name": raw.get("bplcNm", ""),
        "status": raw.get("dtlStateNm", ""),
        "address": raw.get("rdnAdr", ""),
        "region_city": raw.get("ctpvNm", ""),
        "region_district": raw.get("signguNm", ""),
        "phone": raw.get("siteTel") or None,
        "license_no": raw.get("lknStmnyDt") or None,
        "specialty": raw.get("uptaeNm") or None,
    }


def extract_hospitals(response: dict) -> list:
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_hospital_item(item) for item in items]
    except (KeyError, TypeError):
        return []
