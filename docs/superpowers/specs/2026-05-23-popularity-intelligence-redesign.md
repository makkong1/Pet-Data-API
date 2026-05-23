# pet-data-api 재설계 스펙: Popularity Intelligence API

**날짜:** 2026-05-23  
**상태:** 승인됨  
**방향:** Approach A — 완전 클린 슬레이트

---

## 1. 배경 및 목표

### 현재 문제

기존 코드는 두 가지 다른 성격의 로직이 한 서버에 섞여 있다.

- **배치 축**: 공공 API → PostgreSQL, Naver 블로그 → Redis (미리 조사·저장)
- **실시간 축**: 요청 순간에 Naver 블로그 검색 + Kakao 장소 검색 + 공공 DB 반경 조회 + 두 단계 랭킹 (`POST /recommend` 392줄)

결과적으로 코드가 지저분해지고, "미리 조사해서 쌓아두었다가 돌려준다"는 단순한 멘탈 모델과 실제 동작이 달라 유지보수가 어렵다.

### 새 역할 정의

```
Python 서버 = "인기도 인텔리전스 API"

아는 것:  어떤 상호가 최근 블로그/SNS에 얼마나 많이 언급되는가
모르는 것: 사용자 위치, 시설 DB, 지도 정보
```

Petory(Java 서버)가 위치 기반 시설 검색을 담당하고, Python 서버는 인기도 데이터를 사전 집계해서 제공한다. Petory는 자신의 시설 목록과 Python 서버의 인기도를 합쳐 사용자에게 보여준다.

---

## 2. 시스템 구조

```
매일 18:00 배치
  Naver Blog API
      ↓ 9개 context × 2~3 쿼리
  blog.py (상호명 추출 + 언급 집계)
      ↓
  Redis
  popular:{context}  →  [{name, mention_count, avg_freshness, score}, ...]
  trend:{context}    →  sorted set (기존)
      ↓
GET /popular/{context}   ← Petory 호출
GET /trends/{context}    ← Petory 호출
```

**Petory 흐름:**
```
사용자: "주변 미용실 보여줘"
  → Petory: 자기 DB에서 주변 시설 조회
  → Petory: GET /popular/grooming (Python 서버, 비동기)
  → UI: 시설 목록 + 인기 뱃지 합쳐서 표시
```

---

## 3. 인기도 정의 및 score 수식

### 정의

> **인기 = 최근 블로그/SNS에서 해당 상호명이 언급된 횟수 × 최신성 가중치**

### 수식 (고정)

```
# 포스팅 단위 freshness
freshness_weight(post_date):
    age_days = (today - post_date).days
    if age_days > 180: return 0.0
    return max(0.0, 1.0 - age_days / 180.0)
    # 오늘 → 1.0 / 90일 전 → 0.5 / 180일 초과 → 0.0

# 상호명 단위 집계
mention_count(e)  = 해당 상호를 언급한 고유 글(link) 수
avg_freshness(e)  = Σ freshness_weight(post_i) / mention_count(e)
                    ∈ [0.0, 1.0]

# 최종 score (v1 — 선형)
raw_score(e) = mention_count(e) × avg_freshness(e)
score(e)     = raw_score(e) / max(raw_score 전체)
               ∈ [0.0, 1.0]
```

**미래 옵션** (브랜드·체인 과대평가 방지 시):
```
raw_score(e) = log1p(mention_count(e)) × avg_freshness(e)
```
v1에서는 적용하지 않는다. 운영 데이터 보고 판단.

---

## 4. 배치 파이프라인

### 호출량

```
9 contexts × 평균 2~3 쿼리 = 약 22~27 HTTP 요청/일
Naver 블로그 API 일일 한도: 25,000회 → 여유 충분
각 요청: display=100 (페이지네이션 없음)
```

### 추출 파이프

```
Naver Blog API (query당 최대 100건)
    ↓
제목 + 스니펫 텍스트
    ↓
1차 추출: context별 regex suffix/prefix 패턴
    예) ([가-힣a-zA-Z0-9]{2~10})\s*(?:미용실|그루밍샵|...)
    ↓
2차 필터 (기존 파이프라인 유지):
    BLOCKLIST_EXACT / BLOCKLIST_CONTAINS / LOCATION_CITY /
    GRAMMAR_ENDING / 최소 한글 2자 이상
    → _is_valid_name() 통과한 것만
    ↓
중복 처리: 같은 글(link)에서 동일 상호 → 1표만
    ↓
집계: mention_count >= 2 미만 제거 (노이즈)
상위 20개만 유지 (score 내림차순)
```

### Redis 저장 스키마

```
KEY:   popular:{context}
VALUE: JSON 배열 (최대 20개)
TTL:   25h (24h 배치 주기 + 1h 여유)

[
  {
    "name":          "해피독",
    "mention_count": 12,
    "avg_freshness": 0.85,
    "score":         1.0
  },
  ...
]
```

### 실패 처리

| 상황 | 처리 |
|------|------|
| Naver 장애 (예외) | 해당 context 건너뛰고 나머지 계속 |
| 후보 0개 (mention_count >= 2 없음) | Redis 갱신 생략 → 이전 스냅샷 TTL 25h 유지 |
| Redis 장애 | 저장 실패 로그 남기고 계속 (GET에서 503 반환) |

---

## 5. API 스펙

### GET /popular/{context}

```
인증:  X-API-Key 헤더

Path params:
  context: grooming | hospital | supplies | pharmacy |
           cafe | pension | restaurant | boarding | hotel

Query params:
  limit: int  default=20  max=20

  context 별칭 허용 (기존 호환):
    snack, food, clothes → supplies 로 정규화

Response 200:
[
  {
    "name":          "해피독",
    "mention_count": 12,
    "avg_freshness": 0.85,
    "score":         1.0
  }
]

Response 404:  {"detail": "Unknown context: {context}"}
Response 503:  {"detail": "popular data unavailable"}
               (Redis에 해당 context 키 없음 — 배치 미실행 또는 전체 장애)
```

### GET /trends/{context}

기존 동작 유지. 변경 없음.

### POST /collect/trigger

```
인증:  X-ADMIN-API-Key 헤더

Body:
{
  "targets": ["popular", "trends"]
}

Response 202:
{
  "message": "collection started",
  "targets": ["popular", "trends"]
}
```

---

## 6. 파일 구조

### 새 구조 (약 25개 파일)

```
app/
├── main.py                        # 라우터 3개
├── ingestion/
│   ├── naver.py                   # Naver API 클라이언트 (유지)
│   ├── blog.py                    # grooming_blog.py → 리네임·일반화
│   ├── runner.py                  # 배치 실행 (단순화)
│   └── analyzer/
│       ├── morpheme.py
│       └── trend.py
├── serving/
│   └── api/
│       ├── popular.py             # 신규
│       ├── trends.py              # 유지
│       └── collect.py             # 단순화
└── platform/
    ├── cache/redis.py
    ├── core/
    │   ├── config.py              # 환경변수 절반 삭제
    │   └── auth.py
    ├── schemas/
    │   └── popular.py             # 신규
    ├── observability.py
    └── scheduler/jobs.py          # 단순화
```

### 삭제 목록

```
# ingestion
app/ingestion/kakao.py
app/ingestion/geocoder.py
app/ingestion/business.py
app/ingestion/hospital.py
app/ingestion/pharmacy.py
app/ingestion/client.py
app/ingestion/trend_history.py
app/ingestion/grooming_blog.py    → blog.py로 대체

# serving
app/serving/api/recommend.py
app/serving/api/facilities.py
app/serving/api/stats.py
app/serving/api/search.py
app/serving/api/events.py
app/serving/recommender/          (디렉터리 전체)

# platform
app/platform/core/database.py
app/platform/models/              (디렉터리 전체)
app/platform/schemas/facility.py
app/platform/schemas/recommend.py
app/platform/schemas/stats.py
app/platform/schemas/events.py

# 루트
migrations/                       (디렉터리 전체)
```

### 환경변수

```
삭제:
  DATABASE_URL
  KAKAO_REST_API_KEY, KAKAO_TIMEOUT_MS
  OLLAMA_BASE_URL, OLLAMA_MODEL
  GROOMING_MVP_ENABLED
  PUBLIC_DATA_API_KEY, HOSPITAL_API_KEY

유지:
  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, NAVER_TIMEOUT_MS
  REDIS_URL
  API_KEY_HASH, ADMIN_API_KEY_HASH
```

---

## 7. 테스트 계획

### 삭제

```
test_grooming_ranker.py
test_kakao_client.py
test_kakao_place_filter.py
test_recommend_api.py
test_facilities_api.py
test_recommender.py
test_grooming_blog_mvp.py
test_ranker.py
test_business_collector.py
test_hospital_collector.py
test_geocoder.py
test_collect_api.py (부분 — popular trigger 제외)
```

### 신규

```
test_blog.py
  - 상호명 추출 로직 (기존 test_grooming_blog.py 리팩터)
  - context별 패턴 테스트
  - 노이즈 필터 회귀 테스트

test_popular_api.py
  - GET /popular/{context} 정상 응답
  - Redis 데이터 없을 때 503
  - 미지원 context 404
  - limit 파라미터

test_score.py
  - freshness_weight(date) 계산 검증
  - avg_freshness 수식 검증
  - score 정규화 [0.0, 1.0] 범위
```

---

## 8. 마이그레이션 고려사항

- **Petory 연동 변경 필요**: 기존 `POST /recommend` 호출 → `GET /popular/{context}` + `GET /trends/{context}` 두 번으로 변경
- **PostgreSQL 제거**: `DATABASE_URL` 불필요. 로컬 실행 시 PostgreSQL 프로세스 불필요
- **기존 Redis 키**: `trend:*` 키는 그대로 사용. `popular:*` 키 신규 추가
- **POST /collect/trigger body 변경**: 기존 호출자(관리자)가 `targets` 파라미터 추가 필요. Petory는 이 엔드포인트를 호출하지 않으므로 영향 없음
