# Pet Facilities API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공공데이터(영업장 + 동물병원) 수집 파이프라인과 REST API를 구현해 Petory 서버에 시설 데이터를 제공한다.

**Architecture:** 기존 FastAPI + SQLAlchemy + APScheduler 아키텍처를 재사용한다. DB 스키마(v2)는 이미 적용 완료. `app/core/` (config, database, auth)는 변경 없이 그대로 사용한다. 새 코드는 models, schemas, collector, api 레이어를 순서대로 구현한다.

**Tech Stack:** Python 3.9, FastAPI, SQLAlchemy 2.0 async, asyncpg, httpx, APScheduler, pytest-asyncio

---

> **주의:** 이 프로젝트는 `/Users/maknkkong/project/pet-data-api/` 기준. venv 활성화 필수.  
> **Env prefix for pytest:**  
> `DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy"`

---

### Task 1: SQLAlchemy 모델 (PetFacility, BusinessDetail, HospitalDetail)

**Files:**
- Create: `app/models/facility.py`
- Create: `app/models/details.py`
- Modify: `app/models/__init__.py` (빈 파일 유지)
- Create: `tests/test_facility_models.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_facility_models.py`:
```python
from app.models.facility import PetFacility
from app.models.details import BusinessDetail, HospitalDetail


def test_pet_facility_tablename():
    assert PetFacility.__tablename__ == "pet_facilities"


def test_business_detail_tablename():
    assert BusinessDetail.__tablename__ == "business_details"


def test_hospital_detail_tablename():
    assert HospitalDetail.__tablename__ == "hospital_details"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/test_facility_models.py -v 2>&1 | head -15
```
Expected: ImportError

- [ ] **Step 3: facility.py 모델 작성**

`app/models/facility.py`:
```python
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PetFacility(Base):
    __tablename__ = "pet_facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    region_city: Mapped[str] = mapped_column(String(50), nullable=False)
    region_district: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: details.py 모델 작성**

`app/models/details.py`:
```python
from typing import Optional
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class BusinessDetail(Base):
    __tablename__ = "business_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("pet_facilities.id", ondelete="CASCADE"), nullable=False)
    business_type: Mapped[str] = mapped_column(String(50), nullable=False)
    registration_no: Mapped[Optional[str]] = mapped_column(String(100))


class HospitalDetail(Base):
    __tablename__ = "hospital_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(Integer, ForeignKey("pet_facilities.id", ondelete="CASCADE"), nullable=False)
    license_no: Mapped[Optional[str]] = mapped_column(String(100))
    specialty: Mapped[Optional[str]] = mapped_column(String(100))
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/test_facility_models.py -v
```
Expected: 3 PASSED

- [ ] **Step 6: 커밋**

```bash
git add app/models/facility.py app/models/details.py tests/test_facility_models.py
git commit -m "feat: PetFacility, BusinessDetail, HospitalDetail SQLAlchemy 모델"
```

---

### Task 2: Pydantic 스키마

**Files:**
- Create: `app/schemas/facility.py`
- Modify: `app/schemas/stats.py` (SummaryResponse 추가)

- [ ] **Step 1: facility.py 스키마 작성**

`app/schemas/facility.py`:
```python
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel


class FacilityResponse(BaseModel):
    id: int
    source_id: str
    type: str
    name: str
    status: str
    address: str
    region_city: str
    region_district: str
    phone: Optional[str]
    collected_at: datetime

    model_config = {"from_attributes": True}


class FacilityListResponse(BaseModel):
    items: List[FacilityResponse]
    next_cursor: Optional[int]
    has_next: bool


class FacilityDetailResponse(BaseModel):
    id: int
    source_id: str
    type: str
    name: str
    status: str
    address: str
    region_city: str
    region_district: str
    phone: Optional[str]
    collected_at: datetime
    details: Dict[str, Any]

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: stats.py에 SummaryResponse 추가**

`app/schemas/stats.py` 전체 교체:
```python
from pydantic import BaseModel


class SummaryResponse(BaseModel):
    type: str
    region_city: str
    region_district: str
    count: int
```

- [ ] **Step 3: import 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" python3 -c "
from app.schemas.facility import FacilityResponse, FacilityListResponse, FacilityDetailResponse
from app.schemas.stats import SummaryResponse
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: 커밋**

```bash
git add app/schemas/facility.py app/schemas/stats.py
git commit -m "feat: Pydantic 스키마 (FacilityResponse, FacilityDetailResponse, SummaryResponse)"
```

---

### Task 3: 공통 HTTP 클라이언트 + 영업장 수집기

**Files:**
- Modify: `app/collector/client.py` (범용 클라이언트로 교체)
- Create: `app/collector/business.py`
- Create: `tests/test_business_collector.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_business_collector.py`:
```python
from app.collector.business import parse_business_item


def test_parse_business_item_maps_fields():
    raw = {
        "bsnNm": "행복 펫 미용",
        "bsnStts": "영업",
        "rdnAdr": "서울특별시 강남구 테헤란로 123",
        "ctpvNm": "서울특별시",
        "signguNm": "강남구",
        "telNo": "02-1234-5678",
        "mgtNo": "BIZ-001",
        "uptaeNm": "동물미용업",
    }
    result = parse_business_item(raw)
    assert result["name"] == "행복 펫 미용"
    assert result["status"] == "영업"
    assert result["region_city"] == "서울특별시"
    assert result["region_district"] == "강남구"
    assert result["type"] == "BUSINESS"
    assert result["business_type"] == "동물미용업"


def test_parse_business_item_missing_phone():
    raw = {
        "bsnNm": "테스트",
        "bsnStts": "영업",
        "rdnAdr": "서울특별시 강남구 어딘가",
        "ctpvNm": "서울특별시",
        "signguNm": "강남구",
        "mgtNo": "BIZ-002",
        "uptaeNm": "동물위탁관리업",
    }
    result = parse_business_item(raw)
    assert result["phone"] is None
    assert result["source_id"] == "BIZ-002"
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/test_business_collector.py -v 2>&1 | head -10
```
Expected: ImportError

- [ ] **Step 3: client.py 범용 클라이언트로 교체**

`app/collector/client.py`:
```python
import asyncio
import httpx
from typing import Optional

RETRY_DELAYS = [1, 2, 4]


async def fetch_public_api(url: str, params: dict, timeout: int = 30) -> dict:
    last_error: Optional[Exception] = None
    for delay in [0] + RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            last_error = e
    raise last_error
```

- [ ] **Step 4: business.py 작성**

`app/collector/business.py`:
```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/test_business_collector.py -v
```
Expected: 2 PASSED

- [ ] **Step 6: 커밋**

```bash
git add app/collector/client.py app/collector/business.py tests/test_business_collector.py
git commit -m "feat: 공통 HTTP 클라이언트, 영업장 수집기 (business collector)"
```

---

### Task 4: 동물병원 수집기

**Files:**
- Create: `app/collector/hospital.py`
- Create: `tests/test_hospital_collector.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_hospital_collector.py`:
```python
from app.collector.hospital import parse_hospital_item


def test_parse_hospital_item_maps_fields():
    raw = {
        "bplcNm": "강남동물병원",
        "dtlStateNm": "영업",
        "rdnAdr": "서울특별시 강남구 봉은사로 123",
        "ctpvNm": "서울특별시",
        "signguNm": "강남구",
        "siteTel": "02-9876-5432",
        "mgtNo": "HOSP-001",
        "uptaeNm": "동물병원",
    }
    result = parse_hospital_item(raw)
    assert result["name"] == "강남동물병원"
    assert result["status"] == "영업"
    assert result["region_city"] == "서울특별시"
    assert result["region_district"] == "강남구"
    assert result["type"] == "HOSPITAL"
    assert result["source_id"] == "HOSP-001"


def test_parse_hospital_item_missing_phone():
    raw = {
        "bplcNm": "테스트병원",
        "dtlStateNm": "영업",
        "rdnAdr": "경기도 수원시 어딘가",
        "ctpvNm": "경기도",
        "signguNm": "수원시",
        "mgtNo": "HOSP-002",
        "uptaeNm": "동물병원",
    }
    result = parse_hospital_item(raw)
    assert result["phone"] is None
    assert result["license_no"] is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/test_hospital_collector.py -v 2>&1 | head -10
```
Expected: ImportError

- [ ] **Step 3: hospital.py 작성**

`app/collector/hospital.py`:
```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/test_hospital_collector.py -v
```
Expected: 2 PASSED

- [ ] **Step 5: 커밋**

```bash
git add app/collector/hospital.py tests/test_hospital_collector.py
git commit -m "feat: 동물병원 수집기 (hospital collector)"
```

---

### Task 5: 수집 오케스트레이터 (runner.py)

**Files:**
- Modify: `app/collector/runner.py` (전체 교체)

- [ ] **Step 1: runner.py 작성**

`app/collector/runner.py`:
```python
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.collector.business import fetch_businesses, extract_businesses
from app.collector.hospital import fetch_hospitals, extract_hospitals
from app.models.log import CollectionLog


async def _upsert_facility(db: AsyncSession, item: dict) -> bool:
    if not item.get("source_id") or not item.get("name"):
        return False

    facility_type = item["type"]

    await db.execute(
        text("""
            INSERT INTO pet_facilities
                (source_id, type, name, status, address,
                 region_city, region_district, phone, collected_at)
            VALUES
                (:source_id, :type, :name, :status, :address,
                 :region_city, :region_district, :phone, NOW())
            ON CONFLICT (source_id) DO UPDATE SET
                name            = EXCLUDED.name,
                status          = EXCLUDED.status,
                address         = EXCLUDED.address,
                region_city     = EXCLUDED.region_city,
                region_district = EXCLUDED.region_district,
                phone           = EXCLUDED.phone,
                collected_at    = NOW()
            RETURNING id
        """),
        item,
    )

    result = await db.execute(
        text("SELECT id FROM pet_facilities WHERE source_id = :source_id"),
        {"source_id": item["source_id"]},
    )
    facility_id = result.scalar_one()

    if facility_type == "BUSINESS":
        await db.execute(
            text("""
                INSERT INTO business_details (facility_id, business_type, registration_no)
                VALUES (:facility_id, :business_type, :registration_no)
                ON CONFLICT (facility_id) DO UPDATE SET
                    business_type   = EXCLUDED.business_type,
                    registration_no = EXCLUDED.registration_no
            """),
            {
                "facility_id": facility_id,
                "business_type": item.get("business_type", ""),
                "registration_no": item.get("registration_no"),
            },
        )
    elif facility_type == "HOSPITAL":
        await db.execute(
            text("""
                INSERT INTO hospital_details (facility_id, license_no, specialty)
                VALUES (:facility_id, :license_no, :specialty)
                ON CONFLICT (facility_id) DO UPDATE SET
                    license_no = EXCLUDED.license_no,
                    specialty  = EXCLUDED.specialty
            """),
            {
                "facility_id": facility_id,
                "license_no": item.get("license_no"),
                "specialty": item.get("specialty"),
            },
        )
    return True


async def _collect_source(
    db: AsyncSession,
    source_name: str,
    fetch_fn,
    extract_fn,
) -> CollectionLog:
    log = CollectionLog(
        source=source_name,
        status="failed",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    await db.flush()

    try:
        response = await fetch_fn()
        items = extract_fn(response)
        log.total_fetched = len(items)

        saved = 0
        for item in items:
            if await _upsert_facility(db, item):
                saved += 1

        log.total_saved = saved
        log.status = "success" if saved == len(items) else "partial"
        await db.commit()
    except Exception as e:
        await db.rollback()
        log.error_message = str(e)
        log.status = "failed"
        await db.commit()

    log.finished_at = datetime.utcnow()
    await db.commit()
    return log


async def run_collection(db: AsyncSession) -> list:
    logs = []
    logs.append(await _collect_source(db, "petShop", fetch_businesses, extract_businesses))
    logs.append(await _collect_source(db, "animalHospital", fetch_hospitals, extract_hospitals))
    return logs
```

- [ ] **Step 2: ON CONFLICT 유일 제약 추가 (business_details, hospital_details)**

`business_details`와 `hospital_details`는 `facility_id`에 UNIQUE 제약이 없으면 ON CONFLICT가 동작 안 함. DB에 추가:

```bash
psql -U $(whoami) -d petdata -c "ALTER TABLE business_details ADD CONSTRAINT uq_business_facility UNIQUE (facility_id);"
psql -U $(whoami) -d petdata_test -c "ALTER TABLE business_details ADD CONSTRAINT uq_business_facility UNIQUE (facility_id);"
psql -U $(whoami) -d petdata -c "ALTER TABLE hospital_details ADD CONSTRAINT uq_hospital_facility UNIQUE (facility_id);"
psql -U $(whoami) -d petdata_test -c "ALTER TABLE hospital_details ADD CONSTRAINT uq_hospital_facility UNIQUE (facility_id);"
```
Expected: `ALTER TABLE` 4번

migration 파일에도 반영:
```bash
echo "ALTER TABLE business_details ADD CONSTRAINT uq_business_facility UNIQUE (facility_id);" >> migrations/v2_pet_facilities.sql
echo "ALTER TABLE hospital_details ADD CONSTRAINT uq_hospital_facility UNIQUE (facility_id);" >> migrations/v2_pet_facilities.sql
```

- [ ] **Step 3: import 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" python3 -c "from app.collector.runner import run_collection; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: 커밋**

```bash
git add app/collector/runner.py migrations/v2_pet_facilities.sql
git commit -m "feat: 수집 오케스트레이터 (runner), business/hospital UNIQUE 제약 추가"
```

---

### Task 6: Facilities API

**Files:**
- Create: `app/api/facilities.py`
- Modify: `app/api/stats.py` (SummaryResponse 기반으로 교체)
- Modify: `app/api/collect.py` (run_collection 반환값 변경 대응)
- Create: `tests/test_facilities_api.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_facilities_api.py`:
```python
import hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.core.config.settings.ADMIN_API_KEY_HASH", "different_hash")


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    @asynccontextmanager
    async def mock_session():
        mock = AsyncMock()
        mock.execute.return_value.mappings.return_value = []
        mock.execute.return_value.scalar_one_or_none.return_value = None
        yield mock

    monkeypatch.setattr("app.core.database.AsyncSessionLocal", mock_session)


@pytest.mark.asyncio
async def test_list_facilities_no_key(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/facilities")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_facilities_invalid_key(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/facilities", headers={"X-API-Key": "bad"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_facilities_limit_max(mock_settings):
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/facilities?limit=200", headers=HEADERS)
    assert response.status_code == 422
```

- [ ] **Step 2: facilities.py 작성**

`app/api/facilities.py`:
```python
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.facility import PetFacility
from app.schemas.facility import FacilityListResponse, FacilityResponse, FacilityDetailResponse

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=FacilityListResponse)
async def list_facilities(
    cursor: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    region_city: Optional[str] = None,
    region_district: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    stmt = select(PetFacility)
    if cursor:
        stmt = stmt.where(PetFacility.id > cursor)
    if type:
        stmt = stmt.where(PetFacility.type == type)
    if region_city:
        stmt = stmt.where(PetFacility.region_city == region_city)
    if region_district:
        stmt = stmt.where(PetFacility.region_district == region_district)
    if status_filter:
        stmt = stmt.where(PetFacility.status == status_filter)
    stmt = stmt.order_by(PetFacility.id).limit(limit + 1)

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    has_next = len(items) > limit
    items = items[:limit]
    next_cursor = items[-1].id if has_next and items else None
    return FacilityListResponse(items=items, next_cursor=next_cursor, has_next=has_next)


@router.get("/{facility_id}", response_model=FacilityDetailResponse)
async def get_facility(
    facility_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    result = await db.execute(
        select(PetFacility).where(PetFacility.id == facility_id)
    )
    facility = result.scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found")

    details: dict = {}
    if facility.type == "BUSINESS":
        r = await db.execute(
            text("SELECT business_type, registration_no FROM business_details WHERE facility_id = :fid"),
            {"fid": facility_id},
        )
        row = r.mappings().first()
        if row:
            details = dict(row)
    elif facility.type == "HOSPITAL":
        r = await db.execute(
            text("SELECT license_no, specialty FROM hospital_details WHERE facility_id = :fid"),
            {"fid": facility_id},
        )
        row = r.mappings().first()
        if row:
            details = dict(row)

    return FacilityDetailResponse(
        id=facility.id,
        source_id=facility.source_id,
        type=facility.type,
        name=facility.name,
        status=facility.status,
        address=facility.address,
        region_city=facility.region_city,
        region_district=facility.region_district,
        phone=facility.phone,
        collected_at=facility.collected_at,
        details=details,
    )
```

- [ ] **Step 3: stats.py 교체**

`app/api/stats.py`:
```python
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_api_key
from app.schemas.stats import SummaryResponse

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=List[SummaryResponse])
async def summary_stats(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    result = await db.execute(
        text("""
            SELECT type, region_city, region_district, COUNT(*)::int AS count
            FROM pet_facilities
            WHERE status = '영업'
            GROUP BY type, region_city, region_district
            ORDER BY region_city, region_district, type
        """)
    )
    return [SummaryResponse(**dict(r)) for r in result.mappings()]
```

- [ ] **Step 4: collect.py 수정 (run_collection이 list 반환)**

`app/api/collect.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_admin_key
from app.collector.runner import run_collection

router = APIRouter(prefix="/collect", tags=["admin"])


@router.post("/trigger")
async def trigger_collection(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin_key),
):
    logs = await run_collection(db)
    return [
        {
            "source": log.source,
            "status": log.status,
            "total_fetched": log.total_fetched,
            "total_saved": log.total_saved,
            "error_message": log.error_message,
            "started_at": log.started_at,
            "finished_at": log.finished_at,
        }
        for log in logs
    ]
```

- [ ] **Step 5: main.py 교체**

`app/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.facilities import router as facilities_router
from app.api.stats import router as stats_router
from app.api.collect import router as collect_router
from app.scheduler.jobs import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Pet Facilities API", lifespan=lifespan)
app.include_router(facilities_router)
app.include_router(stats_router)
app.include_router(collect_router)
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/test_facilities_api.py -v
```
Expected: 3 PASSED

전체 테스트도 확인:
```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/ -v 2>&1 | tail -20
```

- [ ] **Step 7: 커밋**

```bash
git add app/api/facilities.py app/api/stats.py app/api/collect.py app/main.py tests/test_facilities_api.py
git commit -m "feat: GET /facilities, GET /facilities/{id}, GET /stats/summary, main.py 교체"
```

---

### Task 7: APScheduler jobs.py 업데이트

**Files:**
- Modify: `app/scheduler/jobs.py`

- [ ] **Step 1: jobs.py 수정 (02:00 스케줄)**

`app/scheduler/jobs.py`:
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import AsyncSessionLocal
from app.collector.runner import run_collection

scheduler = AsyncIOScheduler()


async def scheduled_collection():
    async with AsyncSessionLocal() as db:
        await run_collection(db)


def start_scheduler():
    scheduler.add_job(
        scheduled_collection,
        trigger="cron",
        hour=2,
        minute=0,
        max_instances=1,
        id="daily_collection",
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
```

- [ ] **Step 2: import 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" python3 -c "from app.scheduler.jobs import start_scheduler; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: 전체 테스트 통과 확인**

```bash
source venv/bin/activate && DATABASE_URL="postgresql+asyncpg://maknkkong@localhost:5432/petdata" API_KEY_HASH="dummy" ADMIN_API_KEY_HASH="dummy" PUBLIC_DATA_API_KEY="dummy" pytest tests/ -v 2>&1 | tail -15
```
Expected: 모두 PASSED (기존 테스트 포함)

- [ ] **Step 4: 커밋**

```bash
git add app/scheduler/jobs.py
git commit -m "feat: APScheduler 02:00 수집 스케줄 업데이트"
```

---

## 스펙 커버리지 체크

| 스펙 요구사항 | 구현 태스크 |
|---|---|
| PetFacility, BusinessDetail, HospitalDetail 모델 | Task 1 |
| FacilityResponse, FacilityDetailResponse, SummaryResponse 스키마 | Task 2 |
| 영업장 수집기 (parse + fetch) | Task 3 |
| 동물병원 수집기 (parse + fetch) | Task 4 |
| runner: 두 소스 독립 실행, CollectionLog 기록 | Task 5 |
| GET /facilities (필터 + keyset pagination) | Task 6 |
| GET /facilities/{id} (details JOIN) | Task 6 |
| GET /stats/summary | Task 6 |
| POST /collect/trigger (admin) | Task 6 |
| APScheduler 02:00 수집 | Task 7 |
