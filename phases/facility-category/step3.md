# Step 3: serving — get_nearby_facilities category 필터링 + FacilityResponse category 노출

## 목표
- `get_nearby_facilities`에서 context → category 기반 DB 필터링 적용
- `FacilityResponse`에 `category` 필드 추가 (Step 1에서 스키마 변경은 완료, 여기서는 서빙 로직 적용)
- `GET /facilities` 검색 API에 category 필터 Swagger 문서 정비

## 배경
Step 1/2에서 category 컬럼 추가 및 ingestion 업데이트가 완료됨.
이제 추천 서빙 쪽에서 context를 category로 매핑해 더 정확한 시설을 반환해야 한다.
예: `context=pharmacy` → category='pharmacy' 시설만 반환.

## 변경 파일

### 1. `app/serving/recommender/facilities.py` (수정)

기존 `CONTEXT_TO_FACILITY_TYPE` 매핑 외에 `CONTEXT_TO_CATEGORY` 추가:

```python
CONTEXT_TO_CATEGORY: dict[str, str | None] = {
    "grooming":    "grooming",
    "hospital":    "hospital",
    "pharmacy":    "pharmacy",
    "supplies":    None,   # category 구분 없이 type=BUSINESS 전체
    "cafe":        None,
    "pension":     None,
    "restaurant":  None,
    "boarding":    None,
    "hotel":       None,
}
```

`_HAVERSINE_SQL` 쿼리에 category 조건 동적 추가.
`get_nearby_facilities`에 `category` 파라미터 추가:

```python
async def get_nearby_facilities(
    db: AsyncSession,
    lat: float,
    lng: float,
    context: str,
    radius_km: float,
    top_n: int,
) -> list[dict]:
    normalized_context = normalize_context(context)
    ftype = CONTEXT_TO_FACILITY_TYPE.get(normalized_context)
    category = CONTEXT_TO_CATEGORY.get(normalized_context)
    if ftype is None:
        return []

    # category 유무에 따라 SQL 분기
    if category:
        sql = _HAVERSINE_SQL_WITH_CATEGORY
        params = {"lat": lat, "lng": lng, "ftype": ftype,
                  "category": category, "radius_m": radius_km * 1000, "top_n": top_n}
    else:
        sql = _HAVERSINE_SQL
        params = {"lat": lat, "lng": lng, "ftype": ftype,
                  "radius_m": radius_km * 1000, "top_n": top_n}

    result = await db.execute(text(sql), params)
    ...
```

`_HAVERSINE_SQL_WITH_CATEGORY` 상수 추가 (기존 SQL에 `AND category = :category` 조건 포함):

```python
_HAVERSINE_SQL_WITH_CATEGORY = """
WITH distances AS (
    SELECT id, source_id, name, address, lat, lng,
        6371000 * acos(LEAST(1.0,
            cos(radians(:lat)) * cos(radians(lat)) *
            cos(radians(lng) - radians(:lng)) +
            sin(radians(:lat)) * sin(radians(lat))
        )) AS distance_m
    FROM pet_facilities
    WHERE lat IS NOT NULL
      AND type = :ftype
      AND category = :category
)
SELECT id, source_id, name, address, lat, lng, distance_m
FROM distances
WHERE distance_m <= :radius_m
ORDER BY distance_m
LIMIT :top_n
"""
```

### 2. `app/serving/api/search.py` 검토
기존 search.py에 category 필터가 없으면 추가.
`GET /facilities/search`의 `context` 파라미터가 category와 매핑되도록 주석 업데이트.

## AC (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate

# 전체 테스트 통과
pytest tests/ -v

# smoke test: context→category 매핑 확인
python3 -c "
from app.serving.recommender.facilities import CONTEXT_TO_CATEGORY, normalize_context
assert CONTEXT_TO_CATEGORY['grooming'] == 'grooming'
assert CONTEXT_TO_CATEGORY['hospital'] == 'hospital'
assert CONTEXT_TO_CATEGORY['pharmacy'] == 'pharmacy'
assert CONTEXT_TO_CATEGORY['cafe'] is None
print('CONTEXT_TO_CATEGORY 매핑 OK')
"

# 서버 기동 후 Swagger 확인 (선택)
# uvicorn app.main:app --reload --port 8000
# curl http://localhost:8000/facilities?category=grooming&limit=5 -H "X-API-Key: <key>"
```
