# 반려동물 추천 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pet-data-api에 `/recommend` 엔드포인트를 추가해 Petory 사용자의 위치·반려동물 정보·현재 컨텍스트를 받아 주변 공인 시설 + 트렌드 키워드 + Ollama llama3 추천문을 합쳐 반환한다.

**Architecture:** pet-data-api가 인텔리전스 레이어 역할을 담당한다. 시설은 PostgreSQL Haversine 쿼리로, 트렌드는 Redis Sorted Set으로, 추천문은 Ollama llama3로 생성한다. Petory는 사용자 Pet 정보와 GPS 좌표를 pet-data-api에 POST하고 결과를 화면에 표시한다.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy async / PostgreSQL Haversine / Redis aioredis / httpx / Ollama llama3 | Java 17 / Spring Boot 3 / RestClient / React 19

---

## 파일 맵

### pet-data-api (신규 생성)
| 파일 | 역할 |
|------|------|
| `migrations/add_facility_coords.sql` | `pet_facilities`에 `lat`, `lng` 컬럼 추가 |
| `app/collector/geocoder.py` | 주소 → 좌표 변환 (Kakao API) |
| `app/schemas/recommend.py` | 요청/응답 Pydantic 스키마 |
| `app/recommender/__init__.py` | 패키지 init |
| `app/recommender/facilities.py` | 반경 내 시설 조회 (Haversine SQL) |
| `app/recommender/llm.py` | Ollama llama3 호출 클라이언트 |
| `app/recommender/builder.py` | LLM 프롬프트 생성 |
| `app/api/recommend.py` | `/recommend` 라우터 |
| `tests/test_recommend_api.py` | `/recommend` 엔드포인트 테스트 |
| `tests/test_recommender.py` | 시설 쿼리·프롬프트 빌더 단위 테스트 |

### pet-data-api (수정)
| 파일 | 변경 내용 |
|------|----------|
| `app/models/facility.py` | `lat`, `lng` Optional[float] 컬럼 추가 |
| `app/collector/runner.py` | `_upsert_facility` 후 좌표 없으면 geocode |
| `app/core/config.py` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `KAKAO_REST_API_KEY` 추가 |
| `app/main.py` | recommend 라우터 등록 |
| `.env.example` | 신규 환경변수 항목 추가 |

### Petory (신규 생성)
| 파일 | 역할 |
|------|------|
| `domain/recommendation/client/PetDataApiClient.java` | pet-data-api HTTP 클라이언트 |
| `domain/recommendation/dto/RecommendRequest.java` | 요청 DTO |
| `domain/recommendation/dto/RecommendResponse.java` | 응답 DTO |
| `domain/recommendation/service/RecommendService.java` | Pet 조회 + 클라이언트 조합 |
| `domain/recommendation/controller/RecommendController.java` | `/api/recommend` |

---

## Phase 1: pet-data-api

---

### Task 1: 시설 테이블에 좌표 컬럼 추가

**Files:**
- Create: `migrations/add_facility_coords.sql`
- Modify: `app/models/facility.py`

- [ ] **Step 1: 마이그레이션 SQL 작성**

```sql
-- migrations/add_facility_coords.sql
ALTER TABLE pet_facilities
    ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_facilities_coords
    ON pet_facilities (lat, lng)
    WHERE lat IS NOT NULL;
```

- [ ] **Step 2: 마이그레이션 실행**

```bash
psql -U postgres -d petdata -f migrations/add_facility_coords.sql
```

기대 출력: `ALTER TABLE` / `CREATE INDEX`

- [ ] **Step 3: PetFacility 모델에 컬럼 추가**

`app/models/facility.py` — `phone` 컬럼 아래에 추가:

```python
from typing import Optional
from sqlalchemy import Integer, String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column

# 기존 컬럼들 유지 후 아래 두 줄 추가
lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
```

- [ ] **Step 4: 서버 임시 기동 후 모델 오류 없는지 확인**

```bash
source venv/bin/activate
python -c "from app.models.facility import PetFacility; print('ok')"
```

기대 출력: `ok`

- [ ] **Step 5: Commit**

```bash
git add migrations/add_facility_coords.sql app/models/facility.py
git commit -m "feat: add lat/lng columns to pet_facilities"
```

---

### Task 2: Kakao 지오코더 구현

**Files:**
- Create: `app/collector/geocoder.py`
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: config에 Kakao API 키 추가**

`app/core/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    API_KEY_HASH: str
    ADMIN_API_KEY_HASH: str
    PUBLIC_DATA_API_KEY: str
    HOSPITAL_API_KEY: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    REDIS_URL: str = "redis://localhost:6379/0"
    KAKAO_REST_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 2: .env.example 업데이트**

기존 내용 유지 후 하단에 추가:

```
KAKAO_REST_API_KEY=<카카오 개발자센터 REST API 키>
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

- [ ] **Step 3: geocoder 구현**

`app/collector/geocoder.py`:

```python
from typing import Optional
import httpx
from app.core.config import settings

KAKAO_GEOCODE_URL = "https://dapi.kakao.com/v2/local/search/address.json"


async def geocode_address(address: str) -> Optional[tuple[float, float]]:
    """주소 → (lat, lng). 실패 시 None 반환."""
    if not settings.KAKAO_REST_API_KEY:
        return None
    headers = {"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"}
    params = {"query": address}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(KAKAO_GEOCODE_URL, headers=headers, params=params)
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            if docs:
                return float(docs[0]["y"]), float(docs[0]["x"])  # (lat, lng)
    except Exception:
        pass
    return None
```

- [ ] **Step 4: 단위 테스트 작성 (mock)**

`tests/test_geocoder.py` 신규 생성:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.collector.geocoder import geocode_address


@pytest.mark.asyncio
async def test_geocode_success():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "documents": [{"y": "37.5665", "x": "126.9780"}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.collector.geocoder.settings") as mock_settings, \
         patch("app.collector.geocoder.httpx.AsyncClient") as mock_client_cls:
        mock_settings.KAKAO_REST_API_KEY = "testkey"
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        result = await geocode_address("서울시 마포구 어딘가")

    assert result == (37.5665, 126.9780)


@pytest.mark.asyncio
async def test_geocode_no_key_returns_none():
    with patch("app.collector.geocoder.settings") as mock_settings:
        mock_settings.KAKAO_REST_API_KEY = ""
        result = await geocode_address("서울시 어딘가")
    assert result is None


@pytest.mark.asyncio
async def test_geocode_empty_docs_returns_none():
    mock_response = MagicMock()
    mock_response.json.return_value = {"documents": []}
    mock_response.raise_for_status = MagicMock()

    with patch("app.collector.geocoder.settings") as mock_settings, \
         patch("app.collector.geocoder.httpx.AsyncClient") as mock_client_cls:
        mock_settings.KAKAO_REST_API_KEY = "testkey"
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        result = await geocode_address("존재하지않는주소")
    assert result is None
```

- [ ] **Step 5: 테스트 실행**

```bash
pytest tests/test_geocoder.py -v
```

기대 출력: 3개 PASSED

- [ ] **Step 6: Commit**

```bash
git add app/collector/geocoder.py app/core/config.py .env.example tests/test_geocoder.py
git commit -m "feat: add Kakao geocoder and config for Ollama/Kakao keys"
```

---

### Task 3: 수집 후 지오코딩 연동

**Files:**
- Modify: `app/collector/runner.py`

- [ ] **Step 1: `_upsert_facility` 뒤 좌표 업데이트 로직 추가**

`app/collector/runner.py` — import 구문에 geocoder 추가:

```python
from app.collector.geocoder import geocode_address
```

`_upsert_facility` 함수 마지막 `return True` 직전에 삽입:

```python
    # 좌표 없는 신규/기존 시설 → geocode 시도
    coord_check = await db.execute(
        text("SELECT lat FROM pet_facilities WHERE source_id = :source_id"),
        {"source_id": item["source_id"]},
    )
    if coord_check.scalar_one_or_none() is None:
        coords = await geocode_address(item.get("address", ""))
        if coords:
            lat, lng = coords
            await db.execute(
                text("UPDATE pet_facilities SET lat = :lat, lng = :lng WHERE source_id = :source_id"),
                {"lat": lat, "lng": lng, "source_id": item["source_id"]},
            )
```

- [ ] **Step 2: 기존 테스트 통과 확인**

```bash
pytest tests/test_business_collector.py tests/test_hospital_collector.py -v
```

기대 출력: 전부 PASSED (기존 테스트 회귀 없음)

- [ ] **Step 3: Commit**

```bash
git add app/collector/runner.py
git commit -m "feat: geocode facility address after upsert"
```

---

### Task 4: Recommend 스키마 정의

**Files:**
- Create: `app/schemas/recommend.py`

- [ ] **Step 1: 스키마 작성**

`app/schemas/recommend.py`:

```python
from typing import Optional, List
from pydantic import BaseModel, Field


class PetInfo(BaseModel):
    type: str          # "dog" | "cat" | "etc"
    breed: Optional[str] = None
    age: Optional[str] = None   # "3살", "5개월" 등 자유 형식


class RecommendRequest(BaseModel):
    lat: float = Field(..., description="사용자 위도")
    lng: float = Field(..., description="사용자 경도")
    context: str = Field(..., description="grooming | hospital | snack | food | clothes")
    radius_km: float = Field(3.0, ge=0.5, le=20.0)
    top_n: int = Field(5, ge=1, le=20)
    pet: Optional[PetInfo] = None


class FacilityItem(BaseModel):
    name: str
    distance_m: int
    address: str


class TrendKeyword(BaseModel):
    keyword: str
    score: int


class RecommendResponse(BaseModel):
    context: str
    facilities: List[FacilityItem]
    trends: List[TrendKeyword]
    recommendation: Optional[str]
    generated_at: str
```

- [ ] **Step 2: 스키마 임포트 확인**

```bash
python -c "from app.schemas.recommend import RecommendRequest, RecommendResponse; print('ok')"
```

기대 출력: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/recommend.py
git commit -m "feat: add recommend request/response schemas"
```

---

### Task 5: 반경 내 시설 조회 함수

**Files:**
- Create: `app/recommender/__init__.py`
- Create: `app/recommender/facilities.py`
- Create: `tests/test_recommender.py`

- [ ] **Step 1: 패키지 init 생성**

`app/recommender/__init__.py` — 빈 파일:

```python
```

- [ ] **Step 2: 시설 쿼리 함수 구현**

`app/recommender/facilities.py`:

```python
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CONTEXT_TO_FACILITY_TYPE: dict[str, Optional[str]] = {
    "grooming": "BUSINESS",
    "hospital": "HOSPITAL",
    "snack": None,
    "food": None,
    "clothes": None,
}

VALID_CONTEXTS = set(CONTEXT_TO_FACILITY_TYPE.keys())

_HAVERSINE_SQL = """
WITH distances AS (
    SELECT
        name,
        address,
        6371000 * acos(
            LEAST(1.0,
                cos(radians(:lat)) * cos(radians(lat)) *
                cos(radians(lng) - radians(:lng)) +
                sin(radians(:lat)) * sin(radians(lat))
            )
        ) AS distance_m
    FROM pet_facilities
    WHERE lat IS NOT NULL
      AND type = :ftype
)
SELECT name, address, distance_m
FROM distances
WHERE distance_m <= :radius_m
ORDER BY distance_m
LIMIT :top_n
"""


async def get_nearby_facilities(
    db: AsyncSession,
    lat: float,
    lng: float,
    context: str,
    radius_km: float,
    top_n: int,
) -> list[dict]:
    ftype = CONTEXT_TO_FACILITY_TYPE.get(context)
    if ftype is None:
        return []

    result = await db.execute(
        text(_HAVERSINE_SQL),
        {
            "lat": lat,
            "lng": lng,
            "ftype": ftype,
            "radius_m": radius_km * 1000,
            "top_n": top_n,
        },
    )
    rows = result.mappings().all()
    return [
        {"name": r["name"], "distance_m": int(r["distance_m"]), "address": r["address"]}
        for r in rows
    ]
```

- [ ] **Step 3: 단위 테스트 작성**

`tests/test_recommender.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.recommender.facilities import get_nearby_facilities, VALID_CONTEXTS


@pytest.mark.asyncio
async def test_get_nearby_facilities_no_type_returns_empty():
    """snack/food/clothes는 시설 없음 → 빈 배열."""
    db = AsyncMock()
    result = await get_nearby_facilities(db, 37.5, 126.9, "snack", 3.0, 5)
    assert result == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_nearby_facilities_grooming_returns_rows():
    """grooming context → BUSINESS 타입 시설 반환."""
    mock_row = {"name": "해피독", "distance_m": 320.5, "address": "서울시 마포구"}
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_row]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    result = await get_nearby_facilities(db, 37.5665, 126.978, "grooming", 3.0, 5)

    assert len(result) == 1
    assert result[0]["name"] == "해피독"
    assert result[0]["distance_m"] == 320
    db.execute.assert_called_once()


def test_valid_contexts():
    assert "grooming" in VALID_CONTEXTS
    assert "hospital" in VALID_CONTEXTS
    assert "snack" in VALID_CONTEXTS
```

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/test_recommender.py -v
```

기대 출력: 3개 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/recommender/ tests/test_recommender.py
git commit -m "feat: add nearby facilities query with Haversine SQL"
```

---

### Task 6: Ollama LLM 클라이언트 + 프롬프트 빌더

**Files:**
- Create: `app/recommender/llm.py`
- Create: `app/recommender/builder.py`

- [ ] **Step 1: Ollama 클라이언트 구현**

`app/recommender/llm.py`:

```python
from typing import Optional
import httpx
from app.core.config import settings

OLLAMA_CHAT_PATH = "/api/chat"


async def generate_recommendation(prompt: str) -> Optional[str]:
    """Ollama llama3에 프롬프트 전송 → 추천 텍스트 반환. 실패 시 None."""
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "너는 반려동물 전문 추천 어시스턴트야. "
                    "반드시 한국어로, 3문장 이내로 간결하게 추천해. "
                    "불필요한 서론 없이 바로 추천 내용만 말해."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}{OLLAMA_CHAT_PATH}",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
    except Exception:
        return None
```

- [ ] **Step 2: 프롬프트 빌더 구현**

`app/recommender/builder.py`:

```python
from typing import Optional

CONTEXT_LABELS: dict[str, str] = {
    "grooming": "미용실",
    "hospital": "동물병원",
    "snack": "간식",
    "food": "사료",
    "clothes": "의류",
}


def build_prompt(
    context: str,
    facilities: list[dict],
    trends: list[dict],
    pet: Optional[dict],
) -> str:
    lines = []

    if pet:
        pet_type = pet.get("type", "")
        breed = pet.get("breed", "")
        age = pet.get("age", "")
        pet_desc = " ".join(filter(None, [breed, age, pet_type]))
        lines.append(f"- 반려동물: {pet_desc}")

    context_label = CONTEXT_LABELS.get(context, context)
    lines.append(f"- 찾는 서비스: {context_label}")

    if facilities:
        fac_desc = ", ".join(
            f"{f['name']}({f['distance_m']}m)" for f in facilities[:3]
        )
        lines.append(f"- 주변 시설 (가까운 순): {fac_desc}")
    else:
        lines.append("- 주변 시설 정보 없음")

    if trends:
        kw_desc = ", ".join(t["keyword"] for t in trends[:5])
        lines.append(f"- 요즘 인기 키워드: {kw_desc}")

    return "\n".join(lines) + "\n\n추천해줘."
```

- [ ] **Step 3: 빌더 테스트 추가**

`tests/test_recommender.py` 파일에 추가 (기존 내용 유지):

```python
from app.recommender.builder import build_prompt


def test_build_prompt_with_pet_and_facilities():
    facilities = [{"name": "해피독", "distance_m": 320, "address": "서울"}]
    trends = [{"keyword": "스포팅컷", "score": 41}]
    pet = {"type": "dog", "breed": "말티즈", "age": "2살"}

    prompt = build_prompt("grooming", facilities, trends, pet)

    assert "말티즈" in prompt
    assert "미용실" in prompt
    assert "해피독(320m)" in prompt
    assert "스포팅컷" in prompt


def test_build_prompt_no_facilities():
    prompt = build_prompt("snack", [], [{"keyword": "오리젠", "score": 10}], None)
    assert "주변 시설 정보 없음" in prompt
    assert "오리젠" in prompt


def test_build_prompt_no_pet():
    prompt = build_prompt("hospital", [], [], None)
    assert "반려동물" not in prompt
    assert "동물병원" in prompt
```

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/test_recommender.py -v
```

기대 출력: 6개 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/recommender/llm.py app/recommender/builder.py tests/test_recommender.py
git commit -m "feat: add Ollama LLM client and prompt builder"
```

---

### Task 7: `/recommend` 라우터 + main 등록

**Files:**
- Create: `app/api/recommend.py`
- Modify: `app/main.py`
- Create: `tests/test_recommend_api.py`

- [ ] **Step 1: 실패 테스트 먼저 작성**

`tests/test_recommend_api.py`:

```python
import hashlib
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app

API_KEY = "testkey"
API_KEY_HASH = hashlib.sha256(API_KEY.encode()).hexdigest()
HEADERS = {"X-API-Key": API_KEY}

VALID_PAYLOAD = {
    "lat": 37.5665,
    "lng": 126.9780,
    "context": "grooming",
    "radius_km": 3.0,
    "top_n": 5,
    "pet": {"type": "dog", "breed": "말티즈", "age": "2살"},
}


@pytest.fixture(autouse=True)
def patch_api_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.API_KEY_HASH", API_KEY_HASH)
    monkeypatch.setattr("app.core.config.settings.ADMIN_API_KEY_HASH", "different")


@pytest.mark.asyncio
async def test_recommend_success():
    mock_facilities = [{"name": "해피독", "distance_m": 320, "address": "서울"}]
    mock_trends = [("스포팅컷", 41.0), ("여름컷", 35.0)]
    mock_reco = "말티즈에게는 스포팅컷이 인기입니다."

    with patch("app.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.api.recommend.get_trend", new=AsyncMock(return_value=mock_trends)), \
         patch("app.api.recommend.generate_recommendation", new=AsyncMock(return_value=mock_reco)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["context"] == "grooming"
    assert data["facilities"][0]["name"] == "해피독"
    assert data["trends"][0]["keyword"] == "스포팅컷"
    assert data["recommendation"] == mock_reco


@pytest.mark.asyncio
async def test_recommend_ollama_down_still_returns_data():
    """Ollama 실패해도 시설+트렌드 데이터는 반환."""
    mock_facilities = [{"name": "해피독", "distance_m": 320, "address": "서울"}]

    with patch("app.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=mock_facilities)), \
         patch("app.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=VALID_PAYLOAD, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["recommendation"] is None
    assert len(data["facilities"]) == 1


@pytest.mark.asyncio
async def test_recommend_invalid_context():
    payload = {**VALID_PAYLOAD, "context": "unknown"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/recommend", json=payload, headers=HEADERS)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_recommend_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/recommend", json=VALID_PAYLOAD)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recommend_no_pet():
    payload = {**VALID_PAYLOAD, "pet": None}
    with patch("app.api.recommend.get_nearby_facilities", new=AsyncMock(return_value=[])), \
         patch("app.api.recommend.get_trend", new=AsyncMock(return_value=[])), \
         patch("app.api.recommend.generate_recommendation", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/recommend", json=payload, headers=HEADERS)
    assert response.status_code == 200
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

```bash
pytest tests/test_recommend_api.py -v
```

기대 출력: `ImportError` 또는 `404` (라우터 미등록 상태)

- [ ] **Step 3: `/recommend` 라우터 구현**

`app/api/recommend.py`:

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_api_key
from app.schemas.recommend import RecommendRequest, RecommendResponse, FacilityItem, TrendKeyword
from app.recommender.facilities import get_nearby_facilities, VALID_CONTEXTS
from app.recommender.builder import build_prompt
from app.recommender.llm import generate_recommendation
from app.cache.redis import get_trend, get_updated_at

router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.post("", response_model=RecommendResponse)
async def recommend(
    req: RecommendRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    if req.context not in VALID_CONTEXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown context: {req.context}. Valid: {sorted(VALID_CONTEXTS)}",
        )

    facilities_raw = await get_nearby_facilities(
        db, req.lat, req.lng, req.context, req.radius_km, req.top_n
    )

    try:
        trends_raw = await get_trend(req.context, 10)
    except Exception:
        trends_raw = []

    trends = [TrendKeyword(keyword=k, score=int(s)) for k, s in trends_raw]
    facilities = [FacilityItem(**f) for f in facilities_raw]

    pet_dict = req.pet.model_dump() if req.pet else None
    prompt = build_prompt(req.context, facilities_raw, [t.model_dump() for t in trends], pet_dict)
    recommendation = await generate_recommendation(prompt)

    return RecommendResponse(
        context=req.context,
        facilities=facilities,
        trends=trends,
        recommendation=recommendation,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 4: main.py에 라우터 등록**

`app/main.py`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.facilities import router as facilities_router
from app.api.stats import router as stats_router
from app.api.collect import router as collect_router
from app.api.trends import router as trends_router
from app.api.recommend import router as recommend_router
from app.scheduler.jobs import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Pet Data API", lifespan=lifespan)
app.include_router(facilities_router)
app.include_router(stats_router)
app.include_router(collect_router)
app.include_router(trends_router)
app.include_router(recommend_router)
```

- [ ] **Step 5: 전체 테스트 통과 확인**

```bash
pytest tests/test_recommend_api.py tests/test_recommender.py -v
```

기대 출력: 전부 PASSED

- [ ] **Step 6: 전체 테스트 회귀 확인**

```bash
pytest tests/ -v
```

기대 출력: 전부 PASSED

- [ ] **Step 7: Swagger로 수동 확인**

```bash
uvicorn app.main:app --reload
# http://localhost:8000/docs 에서 POST /recommend 실행
```

- [ ] **Step 8: Commit**

```bash
git add app/api/recommend.py app/main.py tests/test_recommend_api.py
git commit -m "feat: add POST /recommend endpoint with Ollama LLM"
```

---

## Phase 2: Petory

> Petory 레포 (`/Users/maknkkong/project/Petory`)에서 작업한다.
> 모든 파일의 기본 패키지: `com.linkup.Petory`

---

### Task 8: PetDataApiClient + DTOs

**Files:**
- Create: `backend/main/java/com/linkup/Petory/domain/recommendation/dto/PetInfoDto.java`
- Create: `backend/main/java/com/linkup/Petory/domain/recommendation/dto/RecommendRequest.java`
- Create: `backend/main/java/com/linkup/Petory/domain/recommendation/dto/FacilityItem.java`
- Create: `backend/main/java/com/linkup/Petory/domain/recommendation/dto/TrendKeyword.java`
- Create: `backend/main/java/com/linkup/Petory/domain/recommendation/dto/RecommendResponse.java`
- Create: `backend/main/java/com/linkup/Petory/domain/recommendation/client/PetDataApiClient.java`
- Modify: `backend/main/resources/application.properties`

- [ ] **Step 1: application.properties에 pet-data-api 설정 추가**

```properties
pet-data-api.base-url=http://localhost:8000
pet-data-api.api-key=${PET_DATA_API_KEY:test-api-key}
```

- [ ] **Step 2: DTO 클래스 작성**

`PetInfoDto.java`:

```java
package com.linkup.Petory.domain.recommendation.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Builder;

@Builder
@JsonInclude(JsonInclude.Include.NON_NULL)
public record PetInfoDto(String type, String breed, String age) {}
```

`RecommendRequest.java`:

```java
package com.linkup.Petory.domain.recommendation.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Builder;

@Builder
@JsonInclude(JsonInclude.Include.NON_NULL)
public record RecommendRequest(
    double lat,
    double lng,
    String context,
    @JsonProperty("radius_km") double radiusKm,
    @JsonProperty("top_n") int topN,
    PetInfoDto pet
) {}
```

`FacilityItem.java`:

```java
package com.linkup.Petory.domain.recommendation.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record FacilityItem(
    String name,
    @JsonProperty("distance_m") int distanceM,
    String address
) {}
```

`TrendKeyword.java`:

```java
package com.linkup.Petory.domain.recommendation.dto;

public record TrendKeyword(String keyword, int score) {}
```

`RecommendResponse.java`:

```java
package com.linkup.Petory.domain.recommendation.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record RecommendResponse(
    String context,
    List<FacilityItem> facilities,
    List<TrendKeyword> trends,
    String recommendation,
    @JsonProperty("generated_at") String generatedAt
) {}
```

- [ ] **Step 3: HTTP 클라이언트 구현**

`PetDataApiClient.java`:

```java
package com.linkup.Petory.domain.recommendation.client;

import com.linkup.Petory.domain.recommendation.dto.RecommendRequest;
import com.linkup.Petory.domain.recommendation.dto.RecommendResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Slf4j
@Component
public class PetDataApiClient {

    private final RestClient restClient;

    public PetDataApiClient(
            @Value("${pet-data-api.base-url}") String baseUrl,
            @Value("${pet-data-api.api-key}") String apiKey
    ) {
        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .defaultHeader("X-API-Key", apiKey)
                .defaultHeader("Content-Type", "application/json")
                .build();
    }

    public RecommendResponse recommend(RecommendRequest request) {
        try {
            return restClient.post()
                    .uri("/recommend")
                    .body(request)
                    .retrieve()
                    .body(RecommendResponse.class);
        } catch (Exception e) {
            log.warn("pet-data-api 추천 요청 실패: {}", e.getMessage());
            return null;
        }
    }
}
```

- [ ] **Step 4: Commit**

```bash
# Petory 레포에서
git add backend/main/java/com/linkup/Petory/domain/recommendation/ \
        backend/main/resources/application.properties
git commit -m "feat: add PetDataApiClient and recommendation DTOs"
```

---

### Task 9: RecommendService + RecommendController

**Files:**
- Create: `backend/main/java/com/linkup/Petory/domain/recommendation/service/RecommendService.java`
- Create: `backend/main/java/com/linkup/Petory/domain/recommendation/controller/RecommendController.java`

- [ ] **Step 1: RecommendService 구현**

`RecommendService.java`:

```java
package com.linkup.Petory.domain.recommendation.service;

import com.linkup.Petory.domain.recommendation.client.PetDataApiClient;
import com.linkup.Petory.domain.recommendation.dto.PetInfoDto;
import com.linkup.Petory.domain.recommendation.dto.RecommendRequest;
import com.linkup.Petory.domain.recommendation.dto.RecommendResponse;
import com.linkup.Petory.domain.user.entity.Pet;
import com.linkup.Petory.domain.user.repository.PetRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class RecommendService {

    private final PetDataApiClient petDataApiClient;
    private final PetRepository petRepository;

    public RecommendResponse recommend(
            Long userId,
            double lat,
            double lng,
            String context
    ) {
        PetInfoDto petInfo = buildPetInfo(userId);

        RecommendRequest request = RecommendRequest.builder()
                .lat(lat)
                .lng(lng)
                .context(context)
                .radiusKm(3.0)
                .topN(5)
                .pet(petInfo)
                .build();

        return petDataApiClient.recommend(request);
    }

    private PetInfoDto buildPetInfo(Long userId) {
        List<Pet> pets = petRepository.findByUserIdxAndIsDeletedFalse(userId);
        if (pets.isEmpty()) return null;

        Pet pet = pets.get(0);
        return PetInfoDto.builder()
                .type(pet.getPetType().name().toLowerCase())
                .breed(pet.getBreed())
                .age(pet.getAge())
                .build();
    }
}
```

- [ ] **Step 2: PetRepository에 메서드 확인/추가**

`PetRepository.java` (또는 `SpringDataJpaPetRepository.java`)에 아래 메서드가 없으면 추가:

```java
List<Pet> findByUserIdxAndIsDeletedFalse(Long userIdx);
```

- [ ] **Step 3: RecommendController 구현**

`RecommendController.java`:

```java
package com.linkup.Petory.domain.recommendation.controller;

import com.linkup.Petory.domain.recommendation.dto.RecommendResponse;
import com.linkup.Petory.domain.recommendation.service.RecommendService;
import com.linkup.Petory.global.security.AuthenticatedUserIdResolver;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/recommend")
@RequiredArgsConstructor
public class RecommendController {

    private final RecommendService recommendService;
    private final AuthenticatedUserIdResolver authenticatedUserIdResolver;

    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<RecommendResponse> recommend(
            @RequestParam double lat,
            @RequestParam double lng,
            @RequestParam String context
    ) {
        Long userId = authenticatedUserIdResolver.requireCurrentUserIdx();
        RecommendResponse response = recommendService.recommend(userId, lat, lng, context);
        if (response == null) {
            return ResponseEntity.ok(null);
        }
        return ResponseEntity.ok(response);
    }
}
```

- [ ] **Step 4: Petory 빌드 확인**

```bash
cd /Users/maknkkong/project/Petory
./gradlew compileJava
```

기대 출력: `BUILD SUCCESSFUL`

- [ ] **Step 5: Commit**

```bash
git add backend/main/java/com/linkup/Petory/domain/recommendation/
git commit -m "feat: add RecommendService and RecommendController"
```

---

### Task 10: React 프론트엔드 추천 카드

**Files:**
- Create: `frontend/src/components/recommendation/RecommendCard.jsx`
- Create: `frontend/src/api/recommend.js`

- [ ] **Step 1: API 함수 작성**

`frontend/src/api/recommend.js`:

```javascript
import axios from 'axios';

export async function fetchRecommendation(lat, lng, context) {
  const response = await axios.get('/api/recommend', {
    params: { lat, lng, context },
  });
  return response.data;
}

export function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation not supported'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      reject,
      { timeout: 5000 }
    );
  });
}
```

- [ ] **Step 2: RecommendCard 컴포넌트 작성**

`frontend/src/components/recommendation/RecommendCard.jsx`:

```jsx
import { useEffect, useState } from 'react';
import { fetchRecommendation, getCurrentPosition } from '../../api/recommend';

export default function RecommendCard({ context }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!context) return;
    setLoading(true);

    getCurrentPosition()
      .then(({ lat, lng }) => fetchRecommendation(lat, lng, context))
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [context]);

  if (loading) return <p>추천 로딩 중...</p>;
  if (!data) return null;

  return (
    <div className="recommend-card">
      {data.recommendation && (
        <p className="recommendation-text">{data.recommendation}</p>
      )}

      {data.facilities.length > 0 && (
        <section>
          <h4>주변 시설</h4>
          <ul>
            {data.facilities.map((f, i) => (
              <li key={i}>
                {f.name} — {f.distance_m}m
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.trends.length > 0 && (
        <section>
          <h4>인기 키워드</h4>
          <ul>
            {data.trends.map((t, i) => (
              <li key={i}>{t.keyword}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 3: 사용 예시 — 미용실 페이지에서 카드 삽입**

미용실 목록 페이지 컴포넌트 상단에:

```jsx
import RecommendCard from '../recommendation/RecommendCard';

// JSX 안에서
<RecommendCard context="grooming" />
```

병원 페이지: `context="hospital"`, 간식 페이지: `context="snack"`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/recommend.js frontend/src/components/recommendation/
git commit -m "feat: add RecommendCard component with GPS-based recommendation"
```

---

## 전체 검증 체크리스트

- [ ] `pytest tests/ -v` — 전부 PASSED
- [ ] `uvicorn app.main:app --reload` 기동 후 `http://localhost:8000/docs` 에서 `POST /recommend` curl 테스트
- [ ] Ollama 켠 상태 (`ollama serve`)에서 실제 추천 텍스트 생성 확인
- [ ] Petory 서버 기동 후 `GET /api/recommend?lat=37.5&lng=126.9&context=grooming` 응답 확인
