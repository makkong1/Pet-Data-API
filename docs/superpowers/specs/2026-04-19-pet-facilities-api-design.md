# Pet Facilities API — 설계 스펙

**작성일:** 2026-04-19  
**목적:** 공공데이터 기반 반려동물 관련 시설(영업장, 동물병원) 수집 & REST API 제공  
**소비자:** Petory 서버 (Spring Boot) — HTTP REST API 호출 방식

---

## 개요

pet-data-api는 공공데이터포털에서 반려동물 영업장 및 동물병원 정보를 주기적으로 수집해 PostgreSQL에 저장하고, Petory 서버가 REST API로 조회할 수 있도록 제공한다.

---

## 기술 스택

기존 코드 재사용 (아키텍처 동일)

| 역할 | 기술 |
|------|------|
| 웹 프레임워크 | FastAPI |
| DB ORM | SQLAlchemy 2.0 (async/asyncpg) |
| DB | PostgreSQL 15+ |
| 스케줄러 | APScheduler (매일 02:00) |
| HTTP 클라이언트 | httpx (async, 지수 백오프 재시도) |
| 인증 | API Key (X-API-Key 헤더, SHA-256 해싱) |

---

## 데이터 소스

| API | 제공기관 | 설명 |
|-----|---------|------|
| 반려동물 영업장 정보 | 농림축산검역본부 | 미용, 위탁, 판매, 생산 영업장 전국 목록 |
| 동물병원 현황 | 행정안전부 | 전국 동물병원 인허가 정보 |

---

## DB 스키마

### 설계 원칙
- 공통 컬럼은 `pet_facilities`에 집중 (NULL 없음)
- 타입별 고유 컬럼은 별도 테이블로 분리 (1:1 관계)
- 나중에 새 타입 추가 시 기존 테이블 무수정

### `pet_facilities` (공통)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | SERIAL PK | |
| source_id | VARCHAR(100) UNIQUE | 공공데이터 원본 고유키 (upsert 기준) |
| type | VARCHAR(20) NOT NULL | HOSPITAL / BUSINESS |
| name | VARCHAR(200) NOT NULL | 시설명 |
| status | VARCHAR(30) NOT NULL | 영업중 / 폐업 등 |
| address | VARCHAR(300) NOT NULL | 도로명 주소 |
| region_city | VARCHAR(50) NOT NULL | 시도 (서울, 경기 등) |
| region_district | VARCHAR(50) NOT NULL | 시군구 (강남구 등) |
| phone | VARCHAR(20) | 전화번호 |
| collected_at | TIMESTAMP DEFAULT NOW() | 수집 시각 |

### `business_details` (영업장 전용)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | SERIAL PK | |
| facility_id | INT FK → pet_facilities.id | |
| business_type | VARCHAR(50) NOT NULL | 미용/위탁/판매/생산 |
| registration_no | VARCHAR(100) | 영업 등록번호 |

### `hospital_details` (병원 전용)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | SERIAL PK | |
| facility_id | INT FK → pet_facilities.id | |
| license_no | VARCHAR(100) | 허가번호 |
| specialty | VARCHAR(100) | 진료과목 |

### `collection_logs` (기존 유지)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | SERIAL PK | |
| source | VARCHAR(100) NOT NULL | 수집 대상 API명 |
| status | VARCHAR(20) NOT NULL | success / partial / failed |
| total_fetched | INT DEFAULT 0 | |
| total_saved | INT DEFAULT 0 | |
| error_message | TEXT | |
| started_at | TIMESTAMP NOT NULL | |
| finished_at | TIMESTAMP | |

---

## 인덱스 전략

```sql
-- upsert 기준키
UNIQUE INDEX ON pet_facilities(source_id);

-- 핵심 조회 경로: 지역 + 타입 필터
INDEX ON pet_facilities(region_city, region_district, type, status);

-- 수집 시각 (최신 데이터 조회)
INDEX ON pet_facilities(collected_at);

-- FK 조회
INDEX ON business_details(facility_id);
INDEX ON hospital_details(facility_id);
```

---

## API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/facilities` | 시설 목록 (필터, cursor 페이지네이션) | 일반 |
| GET | `/facilities/{id}` | 시설 상세 (타입별 상세 정보 포함) | 일반 |
| GET | `/stats/summary` | 타입·지역별 집계 | 일반 |
| POST | `/collect/trigger` | 수동 수집 트리거 | 관리자 |

### GET /facilities

쿼리 파라미터:
- `type` — HOSPITAL / BUSINESS (선택)
- `region_city` — 시도 (선택)
- `region_district` — 시군구 (선택)
- `status` — 영업중 등 (선택)
- `cursor` — keyset pagination (기본 0)
- `limit` — 1~100 (기본 20)

응답:
```json
{
  "items": [
    {
      "id": 1,
      "type": "BUSINESS",
      "name": "행복한 동물병원",
      "status": "영업중",
      "address": "서울 강남구 ...",
      "region_city": "서울",
      "region_district": "강남구",
      "phone": "02-1234-5678"
    }
  ],
  "next_cursor": 42,
  "has_next": true
}
```

### GET /facilities/{id}

타입에 따라 `details` 필드 구조 다름:

```json
{
  "id": 1,
  "type": "BUSINESS",
  "name": "...",
  "details": {
    "business_type": "미용",
    "registration_no": "..."
  }
}
```

---

## 수집 파이프라인

```
APScheduler (매일 02:00)
    ↓
CollectorRunner
    ├── BusinessCollector (영업장 API)
    │     └── httpx → parse → upsert pet_facilities + business_details
    └── HospitalCollector (병원 API)
          └── httpx → parse → upsert pet_facilities + hospital_details
    ↓
collection_logs 기록
```

- 각 Collector 독립 실행 (하나 실패해도 다른 것 계속)
- httpx 지수 백오프 3회 재시도 (1s → 2s → 4s)
- upsert 기준키: `source_id` (ON CONFLICT DO UPDATE)
- 수집 완료 후 collection_logs에 결과 기록

---

## 인증

기존 방식 그대로:
- 일반 키: 조회 엔드포인트
- 관리자 키: `/collect/trigger`
- SHA-256 해싱, `X-API-Key` 헤더

---

## Petory 연동 방식

```
Petory Spring 서버
    → GET /facilities?type=BUSINESS&region_city=서울&region_district=강남구
    → X-API-Key: {api_key}
    ↓
pet-data-api 응답
    ↓
Petory에서 사용자 위치와 매칭해 추천 로직 처리
```

---

## 프로젝트 구조 (변경 후)

```
app/
├── api/
│   ├── facilities.py     # GET /facilities, GET /facilities/{id}
│   ├── stats.py          # GET /stats/summary
│   └── collect.py        # POST /collect/trigger
├── collector/
│   ├── client.py         # httpx 공통 클라이언트
│   ├── business.py       # 영업장 수집 & 파싱
│   ├── hospital.py       # 병원 수집 & 파싱
│   └── runner.py         # 전체 수집 오케스트레이션
├── models/
│   ├── facility.py       # PetFacility
│   ├── details.py        # BusinessDetail, HospitalDetail
│   └── log.py            # CollectionLog
├── schemas/
│   ├── facility.py       # FacilityResponse, FacilityListResponse, FacilityDetailResponse
│   └── stats.py          # SummaryResponse
├── core/
│   ├── config.py
│   ├── database.py
│   └── auth.py
└── main.py
```
