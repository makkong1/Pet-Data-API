# Step 2: ingestion — pharmacy.py 추가 + 기존 grooming/hospital category 세팅

## 목표
- `pharmacy.py` 신규 생성 (동물약국 공공 API, `1741000` 패턴)
- `business.py` / `hospital.py` 수집 결과에 `category` 값 포함
- `runner.py`에 pharmacy 소스 등록 + `_upsert_facility`에서 category 저장

## 배경
Step 1에서 category 컬럼을 만들었으니, 수집 시점에 category를 채워야 한다.
동물약국 API는 grooming과 동일한 `1741000` 제공기관 패턴을 따른다.
새 API 키가 없으면 `PUBLIC_DATA_API_KEY` 재사용.

## 변경 파일

### 1. `app/ingestion/pharmacy.py` (신규 생성)

```python
from urllib.parse import quote_plus
from typing import Optional
from app.platform.core.config import settings
from app.ingestion.client import fetch_public_api

PHARMACY_API_URL = "https://apis.data.go.kr/1741000/animal_pharmacy/info"
SUCCESS_RESULT_CODES = frozenset({"00", "0"})


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
    result_code = str(header.get("resultCode", "00")).strip()
    if result_code and result_code not in SUCCESS_RESULT_CODES:
        result_msg = header.get("resultMsg", "Unknown error")
        raise RuntimeError(f"Pharmacy API error ({result_code}): {result_msg}")


async def fetch_pharmacies(page: int = 1, num_of_rows: int = 1000) -> dict:
    key = quote_plus(settings.PUBLIC_DATA_API_KEY)
    url = f"{PHARMACY_API_URL}?serviceKey={key}&pageNo={page}&numOfRows={num_of_rows}"
    return await fetch_public_api(url)


async def fetch_all_pharmacies(num_of_rows: int = 100, max_pages: int = 200) -> list[dict]:
    page = 1
    all_items: list[dict] = []

    while page <= max_pages:
        response = await fetch_pharmacies(page=page, num_of_rows=num_of_rows)
        items = extract_pharmacies(response)
        all_items.extend(items)

        total_count = _extract_total_count(response)
        if total_count is not None:
            if len(all_items) >= total_count:
                break
        elif len(items) < num_of_rows:
            break
        page += 1

    return all_items


def parse_pharmacy_item(raw: dict) -> dict:
    addr = raw.get("ROAD_NM_ADDR") or raw.get("LOTNO_ADDR", "")
    region_city, region_district = _parse_region(addr)
    return {
        "source_id": raw.get("MNG_NO", ""),
        "type": "BUSINESS",
        "category": "pharmacy",
        "name": raw.get("BPLC_NM", ""),
        "status": _normalize_status(raw.get("SALS_STTS_NM", "")),
        "address": addr,
        "region_city": region_city,
        "region_district": region_district,
        "phone": raw.get("TELNO") or None,
        "business_type": "동물약국",
        "registration_no": raw.get("MNG_NO") or None,
    }


def extract_pharmacies(response: dict) -> list:
    _validate_response_or_raise(response)
    try:
        items = response["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        return [parse_pharmacy_item(item) for item in items]
    except (KeyError, TypeError):
        return []
```

### 2. `app/ingestion/business.py` (수정)

`parse_business_item` 함수에 `"category": "grooming"` 추가:

```python
def parse_business_item(raw: dict) -> dict:
    addr = raw.get("ROAD_NM_ADDR") or raw.get("LOTNO_ADDR", "")
    region_city, region_district = _parse_region(addr)
    return {
        "source_id": raw.get("MNG_NO", ""),
        "type": "BUSINESS",
        "category": "grooming",   # ← 추가
        "name": raw.get("BPLC_NM", ""),
        ...
    }
```

### 3. `app/ingestion/hospital.py` (수정)

`parse_hospital_item` 함수에 `"category": "hospital"` 추가:

```python
def parse_hospital_item(raw: dict) -> dict:
    ...
    return {
        ...
        "category": "hospital",   # ← 추가
        ...
    }
```

### 4. `app/ingestion/runner.py` (수정)

`_upsert_facility` 함수의 INSERT/UPDATE SQL에 category 추가:

```python
await db.execute(
    text("""
        INSERT INTO pet_facilities
            (source_id, type, category, name, status, address,
             region_city, region_district, phone, collected_at)
        VALUES
            (:source_id, :type, :category, :name, :status, :address,
             :region_city, :region_district, :phone, NOW())
        ON CONFLICT (source_id) DO UPDATE SET
            name            = EXCLUDED.name,
            category        = EXCLUDED.category,
            status          = EXCLUDED.status,
            ...
    """),
    item,
)
```

`run_collection` 함수에 pharmacy 소스 추가:

```python
from app.ingestion.pharmacy import fetch_all_pharmacies

async def run_collection(db: AsyncSession) -> list:
    logs = []
    logs.append(await _collect_source(db, "petShop", fetch_all_businesses))
    logs.append(await _collect_source(db, "animalHospital", fetch_all_hospitals))
    logs.append(await _collect_source(db, "animalPharmacy", fetch_all_pharmacies))  # ← 추가
    return logs
```

**주의**: pharmacy API가 실제로 존재하지 않는 경우, `_collect_source`가 예외를 잡아 "failed" 상태로 기록하므로 다른 수집에 영향 없음.

## AC (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate

# 단위 테스트 통과
pytest tests/ -v

# pharmacy 파싱 함수 smoke test (실제 API 없이)
python3 -c "
from app.ingestion.pharmacy import parse_pharmacy_item
item = parse_pharmacy_item({'MNG_NO': 'P001', 'BPLC_NM': '테스트약국', 'ROAD_NM_ADDR': '서울 마포구 테스트로 1', 'SALS_STTS_NM': '영업'})
assert item['category'] == 'pharmacy', f'category 오류: {item}'
print('OK:', item)
"

# business category 확인
python3 -c "
from app.ingestion.business import parse_business_item
item = parse_business_item({'MNG_NO': 'B001', 'BPLC_NM': '테스트미용', 'ROAD_NM_ADDR': '서울 강남구 테스트로 1', 'SALS_STTS_NM': '영업'})
assert item['category'] == 'grooming', f'category 오류: {item}'
print('OK:', item)
"
```
