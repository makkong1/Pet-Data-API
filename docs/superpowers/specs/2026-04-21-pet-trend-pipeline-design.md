# Pet Trend Pipeline — Design Spec

**Date:** 2026-04-21
**Status:** Approved

---

## 목표

반려동물 관련 블로그 데이터를 수집·분석해 카테고리별 인기 키워드 트렌드를 API로 제공한다.
공공API(시설 정보)와 병행 운영하며, 유저 생성 콘텐츠 기반의 트렌드 레이어를 추가한다.

---

## 코드 정리 (사전 작업)

유기동물 관련 코드는 프로젝트 방향과 맞지 않아 제거한다.

| 대상 | 처리 |
|------|------|
| `app/collector/parser.py` | 삭제 |
| `app/models/animal.py` | 삭제 |
| `migrations/` 내 `abandoned_animals` 테이블 | DROP migration 추가 |
| `collection_logs` 테이블 | 유지 (facility 수집 로그에 계속 사용) |

---

## 파이프라인 흐름

```
[Naver 블로그 검색 API]
      ↓ 카테고리별 키워드로 검색 (최대 100건/요청)
[app/collector/naver.py]
      ↓ title + description 텍스트 수집
[app/analyzer/morpheme.py]
      ↓ kiwipiepy 명사 추출
[app/analyzer/trend.py]
      ↓ 카테고리별 키워드 빈도 집계
[app/cache/redis.py]
      ↓ Redis Sorted Set 저장 (TTL 24h)
[GET /trends/{category}]
      → 상위 N개 인기 키워드 반환
```

---

## 카테고리 및 검색 키워드

```python
CATEGORY_KEYWORDS = {
    "snack":    ["강아지 간식 추천", "고양이 간식 추천"],
    "food":     ["강아지 사료 추천", "고양이 사료 추천"],
    "grooming": ["강아지 미용실 후기", "반려동물 미용"],
    "hospital": ["동물병원 후기", "반려동물 병원 추천"],
    "clothes":  ["강아지 옷 추천", "반려동물 의류"],
}
```

카테고리는 설정 파일에서 관리하여 추후 추가가 용이하도록 한다.

---

## 신규 모듈 구조

```
app/
├── collector/
│   ├── naver.py        ← Naver Search API 호출 (기존 client.py 패턴 재사용)
│   └── runner.py       ← run_collection()에 트렌드 수집 추가
├── analyzer/
│   ├── __init__.py
│   ├── morpheme.py     ← kiwipiepy 기반 명사 추출
│   └── trend.py        ← 카테고리별 빈도 집계 + 정규화
├── cache/
│   ├── __init__.py
│   └── redis.py        ← aioredis 연결, ZADD/ZRANGE 래퍼
└── api/
    └── trends.py       ← GET /trends/{category}
```

---

## Redis 스키마

| Key | Type | TTL | 내용 |
|-----|------|-----|------|
| `trends:{category}:keywords` | Sorted Set | 24h | member=키워드, score=빈도 |
| `trends:{category}:updated_at` | String | 24h | ISO8601 갱신 시각 |

예시:
```
ZADD trends:snack:keywords 42 "오리젠" 38 "로얄캐닌" 31 "퍼스트메이트"
```

---

## API 엔드포인트

### `GET /trends/{category}`

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `category` | path | snack / food / grooming / hospital / clothes |
| `limit` | query | 반환할 키워드 수 (기본 20, 최대 50) |

응답 예시:
```json
{
  "category": "snack",
  "updated_at": "2026-04-21T03:05:00Z",
  "keywords": [
    { "keyword": "오리젠", "score": 42 },
    { "keyword": "로얄캐닌", "score": 38 }
  ]
}
```

인증: 일반 API Key (`X-API-Key`)

---

## 스케줄

| 작업 | 시각 | 설명 |
|------|------|------|
| 시설 수집 (기존) | 매일 02:00 | 공공API 미용업·병원 upsert |
| **트렌드 수집 (신규)** | **매일 03:00** | Naver API → 형태소 → Redis |

`max_instances=1` 유지 (중복 실행 방지)

---

## 환경변수 추가

```
NAVER_CLIENT_ID=<네이버 개발자센터 Client ID>
NAVER_CLIENT_SECRET=<네이버 개발자센터 Client Secret>
REDIS_URL=redis://localhost:6379/0
```

---

## 형태소 분석기: kiwipiepy

- Java 불필요 (`pip install kiwipiepy`)
- 최신 한국어 모델 내장
- 품사 태그 `NNG`(일반명사), `NNP`(고유명사)만 추출
- 불용어 목록: 강아지, 고양이, 반려동물, 추천, 후기 등 (검색 키워드 자체 제외)

---

## 선택 기능 (Optional — 2단계)

1. **일부 사이트 크롤링**: 크롤링 허용 반려동물 쇼핑몰에서 상품명·리뷰 보강
2. **LLM 트렌드 요약**: Claude API로 `/trends/{category}/summary` 엔드포인트 추가

---

## 제약 조건

- Naver 블로그 검색 API: 하루 25,000건 호출 제한 → 카테고리 5개 × 키워드 2개 × 100건 = 1,000건/일 (여유 있음)
- Redis 미연결 시 `/trends` 엔드포인트는 503 반환 (graceful degradation)
- 기존 `/facilities`, `/stats` 엔드포인트 영향 없음
