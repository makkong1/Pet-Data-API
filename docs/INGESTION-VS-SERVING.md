# 수집(Ingestion) vs 서빙(Serving) — 코드 어디가 뭐 하는지

Petory 같은 클라이언트가 **`POST /recommend`로 받는 응답**을 만들 때 쓰는 코드와, **외부 API에서 데이터를 끌어와 DB·Redis를 채우는 코드**는 역할이 다릅니다. 이 문서는 **`app/ingestion/` vs `app/serving/`** 폴더 기준 맵입니다.

상세 흐름도는 [`분석/DATA-AND-API-FLOW.md`](분석/DATA-AND-API-FLOW.md).

---

## 한 장 요약

| 구분 | 하는 일 | 언제 도나 | 주로 쓰는 저장소 |
|------|---------|-----------|------------------|
| **수집 (Ingestion)** | 공공 API·네이버에서 가져와 **적재·집계** | APScheduler, `POST /collect/trigger` | PostgreSQL **쓰기**, Redis **쓰기** |
| **서빙 (Serving)** | 이미 있는 데이터 **읽고 조합**해 JSON 응답 · 일부 분기에서 외부 API 보강 | `GET /facilities*`, `GET /trends`, **`POST /recommend`** (`GROOMING_MVP` 분기 등), `POST /events/recommendation` | PostgreSQL **읽기**, Redis **읽기**, (선택) Kakao/Naver 블로그·LLM |

**공유 레이어:** `app/platform/cache/redis.py`는 수집이 `save_trend`로 **쓰고**, 서빙이 `get_trend`로 **읽습니다**.

---

## 물리 디렉터리

```
app/
├── ingestion/           # 배치 수집(쓰기) + 일부 모듈은 서빙에서 재사용(예: grooming_blog — 상세는 분석/DATA-AND-API-FLOW.md)
│   ├── runner.py       # run_collection, run_trend_collection, run_collection_by_scope
│   ├── business.py, hospital.py, pharmacy.py, naver.py, grooming_blog.py, geocoder.py, client.py
│   └── analyzer/       # 트렌드 수집 직후 형태소·키워드 집계 (kiwipiepy)
├── serving/             # HTTP 서빙 (읽기·조합)
│   ├── api/            # facilities, search, stats, trends, recommend, collect, events
│   └── recommender/
├── platform/            # 설정·DB·ORM·스키마·Redis·스케줄러 (수집·서빙이 함께 씀)
│   ├── core/, models/, schemas/, cache/, scheduler/
└── main.py
```

---

## 폴더·파일 맵

### 수집 (`app/ingestion/`)

| 경로 | 역할 |
|------|------|
| [`app/ingestion/runner.py`](../app/ingestion/runner.py) | 수집 진입: 시설·트렌드·`run_collection_by_scope` |
| [`business.py`](../app/ingestion/business.py), [`hospital.py`](../app/ingestion/hospital.py), [`pharmacy.py`](../app/ingestion/pharmacy.py) | 공공 API fetch |
| [`naver.py`](../app/ingestion/naver.py) | 네이버 블로그 검색 |
| [`geocoder.py`](../app/ingestion/geocoder.py) | 수집 시 주소→좌표 (Kakao) |
| [`client.py`](../app/ingestion/client.py) | HTTP 재시도 공통 |
| [`analyzer/trend.py`](../app/ingestion/analyzer/trend.py), [`morpheme.py`](../app/ingestion/analyzer/morpheme.py) | 키워드 집계 |
| [`app/serving/api/collect.py`](../app/serving/api/collect.py) | 관리자 HTTP 트리거 → `ingestion.runner` 호출 |
| [`app/platform/scheduler/jobs.py`](../app/platform/scheduler/jobs.py) | 정기 수집 스케줄 |

→ **`app/ingestion/*` + `app/platform/scheduler` + `serving/api/collect`** = 데이터 넣는 쪽.

### 서빙 (`app/serving/`)

| 경로 | 역할 |
|------|------|
| [`api/facilities.py`](../app/serving/api/facilities.py), [`stats.py`](../app/serving/api/stats.py), [`trends.py`](../app/serving/api/trends.py) | DB·Redis **조회만** |
| [`api/recommend.py`](../app/serving/api/recommend.py) | 추천 오케스트레이션(DB·Redis·선택 LLM; MVP 분기 시 `grooming_blog`·Kakao) |
| [`recommender/facilities.py`](../app/serving/recommender/facilities.py) | Haversine 등 읽기 쿼리 |
| [`recommender/builder.py`](../app/serving/recommender/builder.py), [`llm.py`](../app/serving/recommender/llm.py) | 추천 문장 |

→ **`app/serving/api/*` + `app/serving/recommender/*`** = 요청 받아 조합하는 쪽.

### 공유·기반

| 경로 | 비고 |
|------|------|
| [`app/platform/cache/redis.py`](../app/platform/cache/redis.py) | `save_trend` ← 수집 / `get_trend` ← 서빙 |
| [`app/platform/core/`](../app/platform/core/) | 설정, DB 세션, API Key |
| [`app/platform/models/`](../app/platform/models/) | SQLAlchemy ORM |
| [`app/platform/schemas/`](../app/platform/schemas/) | 요청·응답 스키마 |
| [`app/platform/scheduler/`](../app/platform/scheduler/) | APScheduler 잡 |

## Petory `POST /recommend` 분기

레거시 분기는 대략 다음과 같다(DB·Redis 재료 + 선택 Ollama):

```
Petory
  → POST /recommend  (app/serving/api/recommend.py)
        → get_nearby_facilities   (recommender/facilities.py)  → PostgreSQL
        → get_trend               (platform/cache/redis.py)
        → generate_recommendation (recommender/llm.py)         → Ollama (선택)
```

`settings.GROOMING_MVP_ENABLED` 이고 확장 컨텍스트인 경우, 같은 핸들러에서 **`extract_context_mentions` 등 `app/ingestion/` 모듈과 Kakao**를 추가로 탄다([`분석/DATA-AND-API-FLOW.md`](분석/DATA-AND-API-FLOW.md) §5). “서빙은 항상 ingestion을 안 탄다”는 말은 이제 정확하지 않다.
