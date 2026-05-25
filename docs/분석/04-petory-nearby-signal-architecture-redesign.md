# Petory Nearby + Signal 아키텍처 재정의

작성일: 2026-05-25 (코드 기반 전면 갱신)

---

## 1. 한 줄 결론

**구조는 이미 대부분 만들어져 있다. 빠진 핵심은 `GET /facilities` 하나다.**

Petory `RecommendService`는 이미 "Petory DB 후보 + blog signal 보정" 패턴을 구현했다.
`FacilitySyncService`도 이미 pet-data-api에서 시설 목록을 당겨오는 코드가 있다.
근데 pet-data-api에 `GET /facilities`가 없어서 매일 01:00에 404 → 빈 응답으로 끝난다.

---

## 2. 현재 실제 코드 상태

### 2.1 Petory `RecommendService` — 이미 구현된 패턴

`RecommendService.java:48`
```java
private static final Set<String> PETORY_OWNED_CONTEXTS = Set.of(
    "grooming", "hospital", "pharmacy", "cafe", "restaurant", "pension");
```

9개 context 중 6개는 이미 `recommendWithPetoryCandidates()` 경로를 탄다:

```
Petory DB (반경 검색) → nearby 후보 20개
                  ↓
pet-data-api GET /popular/{context} → blog signal 20개
                  ↓
mergeNearbyCandidates() → fuzzy name 매칭 → 최종 5개
```

나머지 `boarding`, `hotel`(supplies 포함)은 `recommendWithLegacyProxy()` — pet-data-api에 전체를 위임한다.

### 2.2 fuzzy name 매칭은 이미 구현돼 있다

`RecommendService.java:332`

`buildNameAliases()`가 이미 suffix stripping을 한다:
- "해피독미용실" → `["해피독미용실", "해피독"]`
- "몽몽동물병원" → `["몽몽동물병원", "몽몽"]`

`normalizeFacilityName()`이 소문자 + 비문자 제거를 한다.
점수: `distanceScore × 0.55 + ratingScore × 0.20 + reviewScore × 0.15 + popularityScore × 0.10`

### 2.3 `FacilitySyncService` — 인프라는 이미 있다

`FacilitySyncScheduler.java:15` — 매일 01:00 실행.

`FacilitySyncService.java:35`:
```java
List<PetFacilityDto> facilities = petDataApiClient.fetchAllFacilities(PAGE_SIZE);
```

`PetDataApiClient.java:384`:
```java
facilityClient.get().uri("/facilities").retrieve()...
// 404면 log.warn → empty 반환으로 graceful fallback
```

→ **pet-data-api에 `GET /facilities`가 없어서 매일 01:00에 silent no-op이다.**

### 2.4 `PetFacilityDto` — Petory가 기대하는 스키마

```json
{
  "name": "해피독",
  "category": "grooming",
  "address": "서울시 강남구 ...",
  "region_city": "서울",
  "region_district": "강남구",
  "phone": "02-xxx-xxxx",
  "lat": 37.123,
  "lng": 127.456,
  "status": null
}
```

`FacilitySyncService.categoryLabel()`이 매핑:
- `"grooming"` → category3 `"동물미용"` 으로 저장
- `"hospital"` → category3 `"동물병원"` 으로 저장
- `"hotel"`, `"boarding"` → category 그대로 저장

### 2.5 `LocationService` entity — 실제 DB 구조 요약

```
idx          Long    canonical ID
name         String
category3    String  소분류 기준 — 검색 1순위
address      String
sido/sigungu/eupmyeondong/roadName
latitude, longitude   Double (엔티티 필드; DB POINT 컬럼은 별도)
phone, rating, reviewCount, score
dataSource   String  "PUBLIC" | "PET_DATA_API"
petFriendly  Boolean
```

반경 검색: MySQL `ST_Within` + spatial index. 공간 컬럼명은 `location`.
score 재계산: 매일 00:00 배치 — `0.5 × rating × log10(reviewCount+1) + 0.2 × petFriendly`

---

## 3. 현재 어디가 끊겨 있는가

### 3.1 `GET /facilities` 미구현 — 인게스천 루프 단절

```
[pet-data-api blog/local 수집] → Redis popular cache
                                        ↑ 여기가 끊겨 있음
[FacilitySyncService 01:00] → GET /facilities → 404 → empty
                                        ↓
[LocationService DB 적재] → 안 됨
```

이 하나가 전체 "master 채우기" 루프를 막고 있다.

### 3.2 boarding / hotel이 레거시 경로에 묶여 있다

`PETORY_OWNED_CONTEXTS`에 boarding, hotel이 없으므로:
- Petory DB에 boarding/hotel 시설이 있어도 nearby 검색을 안 함
- pet-data-api의 blog-only 결과를 그대로 반환

원인: Petory DB에 boarding/hotel 데이터가 충분히 없어서 아직 전환 못 한 것.
해결: `GET /facilities` 구현 → FacilitySyncService가 boarding/hotel 시설을 DB에 채움 → PETORY_OWNED_CONTEXTS 편입.

### 3.3 category 문자열 매핑 — 두 곳에서 다르다

`RecommendService.CONTEXT_TO_CATEGORY` (검색 필터용):
```java
"grooming" → "미용"
"hospital" → "동물병원"
```

`FacilitySyncService.categoryLabel()` (DB 저장용):
```java
"grooming" → "동물미용"
"hospital" → "동물병원"
```

grooming이 DB에 "동물미용"으로 저장됐는데 검색 필터는 "미용"으로 조회 → category WHERE miss 가능.

---

## 4. 목표 아키텍처

> **Petory master를 지속적으로 채우는 ingestion pipeline + 블로그/카페는 그 master를 보정하는 signal pipeline**

### 4.1 ingestion pipeline

```
[pet-data-api]
  local_discovery.py (boarding, hotel)       ← Naver Local → blog verify
  blog.py + enrich_with_location (나머지)    ← blog extraction → 위치 보강
      ↓ name, address, lat/lng, phone, category
  GET /facilities  ← 구현 필요
      ↑
[Petory FacilitySyncScheduler] 01:00 daily pull
      ↓
  LocationService DB (dataSource = "PET_DATA_API")
```

### 4.2 signal pipeline

```
[pet-data-api]
  18:10 popular 배치 → Redis popular:{context}
  GET /popular/{context}  ← 이미 구현됨
      ↓
[Petory RecommendService]
  searchLocationServicesByLocation() → nearby 후보 (Petory DB)
  fetchPopular() → blog signal
  mergeNearbyCandidates() → fuzzy match + scoring
      ↓
  최종 추천 응답
```

### 4.3 전체 흐름

```
매일 (pet-data-api)
  18:10  blog/cafe 수집 → Redis popular:{context}   (signal용)
  같은 데이터 → GET /facilities로 노출              (ingestion용)

매일 01:00 (Petory)
  FacilitySyncScheduler → GET /facilities → LocationService DB 적재

사용자 요청 (Petory)
  RecommendService
    ├→ LocationService DB (반경 검색)    → nearby 후보
    └→ GET /popular/{context}            → blog signal
    merge → 최종 응답
```

---

## 5. 구현 필요 항목

### 5.1 (pet-data-api) `GET /facilities` 추가 — 핵심

계약: `PetDataApiClient.fetchFacilitiesPage(cursor, limit)` 가 기대하는 형식

```
GET /facilities?cursor={cursor}&limit={limit}

Response:
{
  "items": [
    {
      "name":            "해피독",
      "category":        "grooming",
      "address":         "서울시 강남구 ...",
      "region_city":     "서울",
      "region_district": "강남구",
      "phone":           "02-xxx-xxxx",
      "lat":             37.123,
      "lng":             127.456,
      "status":          null
    }
  ],
  "next_cursor": 500,
  "has_next": true
}
```

데이터 소스: Redis `popular:{context}` 캐시에 저장된 시설 목록.
- boarding/hotel: `local_discovery.py`가 address, map_x, map_y, telephone 포함해서 저장
- grooming/hospital 등: `enrich_with_location()` 이후 address, map_x, map_y 포함
  - `enrich_with_location`은 Naver Local 호출이 성공한 경우에만 address를 붙임
  - address가 없는 항목은 Petory `FacilitySyncService.isValid()`에서 자동 skip → 제외됨
- `popular:*` 전체 키 스캔 → cursor 기반 페이징
- `region_city`, `region_district`는 Redis 캐시에 없음 → address 문자열에서 파싱 필요
  - 예: "서울시 강남구 ..." → region_city="서울", region_district="강남구"
  - 파싱 실패 시 null 허용 (FacilitySyncService는 address만 필수 체크)

인증: `X-API-Key` 일반 키.

### 5.2 (Petory) boarding / hotel PETORY_OWNED_CONTEXTS 편입

`GET /facilities` 구현 후 FacilitySyncService가 데이터를 채운 뒤:

```java
// RecommendService.java
private static final Set<String> PETORY_OWNED_CONTEXTS = Set.of(
    "grooming", "hospital", "pharmacy", "cafe", "restaurant", "pension",
    "boarding", "hotel");  // 추가
```

전환 조건: 주요 도시 기준 반경 10km 검색에서 boarding/hotel 후보가 평균 5개 이상 나와야 한다.

### 5.3 (pet-data-api) blog.py 7개 context → local_discovery 패턴 전환

현재 boarding/hotel에서 검증된 "Naver Local → blog verify" 2단계를:
grooming, hospital, cafe 등 나머지에도 확장.

`_LOCAL_DISCOVERY_CONTEXTS = {"boarding", "hotel"}` → 전체 context로 확장.

regex `_SUFFIX_PATTERNS` + blocklist 190개 → 단계적 제거.

`GET /facilities` 구현과 독립적으로 진행 가능. 오검출 감소 효과 즉시 발생.

---

## 6. 단계별 실행 순서

### Phase 1. `GET /facilities` 구현 (pet-data-api)

대상: `app/serving/api/facilities.py` 신규
- Redis `popular:*` 스캔 → cursor 기반 페이징
- `PetFacilityDto` 계약 맞추기
- 인증: 일반 API 키

검증: FacilitySyncScheduler 수동 트리거 후 Petory DB `dataSource = "PET_DATA_API"` 행 확인

### Phase 2. category 매핑 통일

- `RecommendService.CONTEXT_TO_CATEGORY`와 `FacilitySyncService.categoryLabel()` 정합성 맞추기
- grooming: 검색 필터를 "동물미용" 또는 "미용" 중 하나로 통일

### Phase 3. boarding / hotel PETORY_OWNED_CONTEXTS 편입 (Petory)

- Phase 1 완료 후 DB 데이터 확인
- `PETORY_OWNED_CONTEXTS`에 추가
- `CONTEXT_TO_CATEGORY` boarding/hotel 매핑 확인

### Phase 4. blog.py 7개 context local_discovery 패턴 전환 (pet-data-api)

- Naver Local 검색 힌트를 context별로 정의
- `_LOCAL_DISCOVERY_CONTEXTS` 전체로 확장
- blocklist 의존 단계적 제거

---

## 7. 현재 코드에서 살릴 것 / 버릴 것

**살릴 것:**

| 코드 | 이유 |
|---|---|
| `local_discovery.py` 2단계 파이프라인 | 이미 검증된 패턴. ingestion·signal 양쪽 재사용 |
| `RecommendService.mergeNearbyCandidates()` | 이미 동작하는 fuzzy match + scoring |
| `FacilitySyncService` + `FacilitySyncScheduler` | 인프라 완성. endpoint만 있으면 동작 |
| Redis popular cache + `GET /popular/{context}` | signal pipeline 핵심. 변경 불필요 |

**전환 대상:**

| 코드 | 방향 |
|---|---|
| `blog.py` `extract_popular_names()` 7개 context | regex 바텀업 → local_discovery 패턴으로 교체 |
| `runner.py` `_LOCAL_DISCOVERY_CONTEXTS` 고정 | 전체 context로 확장 |

**즉시 추가:**

| 항목 | 위치 |
|---|---|
| `GET /facilities` endpoint | `app/serving/api/facilities.py` |

---

## 8. 요약

| 상태 | 항목 |
|---|---|
| ✅ 이미 구현됨 | RecommendService: 6개 context Petory 후보 + blog signal 합산 |
| ✅ 이미 구현됨 | FacilitySyncService: 01:00 daily pull 인프라 |
| ✅ 이미 구현됨 | mergeNearbyCandidates(): fuzzy name 매칭 + scoring |
| ✅ 구현됨 | `GET /facilities` — cursor 기반 페이징, address 필터, name+address 중복제거 |
| ⏳ 다음 단계 | boarding/hotel PETORY_OWNED_CONTEXTS 편입 |
| ⏳ 중간 개선 | blog.py 7개 context local_discovery 패턴 전환 |
| ⚠️ 정합성 | category 문자열 매핑 두 곳 통일 필요 |
