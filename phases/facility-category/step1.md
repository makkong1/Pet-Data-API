# Step 1: DB migration — category 컬럼 추가 + GET /facilities category 필터

## 목표
`pet_facilities` 테이블에 `category VARCHAR(30)` 컬럼을 추가하고,
`GET /facilities` 엔드포인트에 category 쿼리 파라미터 필터를 추가한다.

## 배경
현재 `pet_facilities`는 `type = BUSINESS | HOSPITAL` 만 존재.
추천 컨텍스트(pharmacy, cafe, boarding 등)는 모두 BUSINESS로 매핑되나 실제 구분 불가.
category 컬럼을 추가해 grooming/hospital/pharmacy 등을 구분한다.

## 변경 파일

### 1. `migrations/007_facility_category.sql` (신규 생성)

```sql
-- v7: pet_facilities.category 컬럼 추가
ALTER TABLE pet_facilities
    ADD COLUMN IF NOT EXISTS category VARCHAR(30);

-- 기존 데이터 백필: HOSPITAL → hospital, BUSINESS → grooming (기존은 모두 미용업)
UPDATE pet_facilities SET category = 'hospital' WHERE type = 'HOSPITAL' AND category IS NULL;
UPDATE pet_facilities SET category = 'grooming' WHERE type = 'BUSINESS' AND category IS NULL;

-- 조회 성능용 인덱스
CREATE INDEX IF NOT EXISTS idx_facilities_category
    ON pet_facilities (category)
    WHERE category IS NOT NULL;
```

실행:
```bash
psql -U postgres -d petdata -f migrations/007_facility_category.sql
```

### 2. `app/platform/models/facility.py` (수정)

기존 `PetFacility` 클래스에 `category` 필드 추가:

```python
category: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
```

### 3. `app/platform/schemas/facility.py` (수정)

`FacilityResponse` 및 `FacilityDetailResponse`에 category 필드 추가:

```python
category: Optional[str] = Field(None, description="카테고리 (e.g. grooming | hospital | pharmacy)")
```

`FacilityListResponse`는 변경 없음.

### 4. `app/serving/api/facilities.py` (수정)

`list_facilities` 함수에 category 필터 파라미터 추가:

```python
category: Optional[str] = Query(None, description="카테고리 필터 (e.g. grooming, hospital, pharmacy)")
```

`stmt` 빌드 블록에 추가:
```python
if category:
    stmt = stmt.where(PetFacility.category == category)
```

## AC (Acceptance Criteria)

```bash
# 마이그레이션 확인
psql -U postgres -d petdata -c "\d pet_facilities" | grep category

# 기존 데이터 백필 확인
psql -U postgres -d petdata -c "SELECT category, count(*) FROM pet_facilities GROUP BY category;"

# pytest 통과
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate && pytest tests/ -v
```
