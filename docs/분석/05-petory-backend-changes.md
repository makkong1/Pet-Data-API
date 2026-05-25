# Petory 백엔드 변경 필요 사항

작성일: 2026-05-25
연관 문서: 04-petory-nearby-signal-architecture-redesign.md

---

## 1. 배경

pet-data-api와 Petory 간 아키텍처를 "ingestion pipeline + signal pipeline" 으로 완성하기 위해
Petory 백엔드에서 필요한 변경 사항을 정리한다.

대부분의 구조는 이미 구현돼 있다. 변경은 좁다.

---

## 2. 즉시 반영 필요 (Phase 1~2 완료 후)

### 2.1 `PETORY_OWNED_CONTEXTS` 확장

**파일:** `RecommendService.java:48`

현재:
```java
private static final Set<String> PETORY_OWNED_CONTEXTS = Set.of(
    "grooming", "hospital", "pharmacy", "cafe", "restaurant", "pension");
```

목표:
```java
private static final Set<String> PETORY_OWNED_CONTEXTS = Set.of(
    "grooming", "hospital", "pharmacy", "cafe", "restaurant", "pension",
    "boarding", "hotel");
```

**전환 조건 (선행 필요):**
- pet-data-api `GET /facilities` 구현 완료
- `FacilitySyncService` 1회 이상 실행 후 `dataSource = "PET_DATA_API"` boarding/hotel 데이터 DB에 존재
- 주요 도시(서울, 부산, 대구 기준) 반경 10km 검색 시 boarding/hotel 후보 평균 5개 이상

---

### 2.2 category 매핑 통일

**문제:** `FacilitySyncService.categoryLabel()`의 default case가 English 그대로 저장해
`CONTEXT_TO_CATEGORY`의 Korean 검색 필터와 6개 context에서 miss가 발생한다.

실제 코드 비교:

| context | CONTEXT_TO_CATEGORY (검색 필터) | categoryLabel() (DB 저장) | match |
|---|---|---|---|
| grooming | `"미용"` | `"동물미용"` | ❌ |
| hospital | `"동물병원"` | `"동물병원"` | ✅ |
| pharmacy | `"동물약국"` | `"동물약국"` | ✅ |
| cafe | `"카페"` | `"cafe"` (default) | ❌ |
| restaurant | `"식당"` | `"restaurant"` (default) | ❌ |
| pension | `"펜션"` | `"pension"` (default) | ❌ |
| boarding | `"위탁관리"` | `"boarding"` (default) | ❌ |
| hotel | `"호텔"` | `"hotel"` (default) | ❌ |

**수정 방향: `FacilitySyncService.categoryLabel()` 확장** (권장)

CONTEXT_TO_CATEGORY는 PUBLIC 데이터 기준으로 이미 Korean 값으로 세팅돼 있다.
PET_DATA_API 데이터 저장 쪽을 맞추는 게 더 안전하다.

`FacilitySyncService.java`의 `categoryLabel()`:
```java
private String categoryLabel(String category, String type) {
    if (StringUtils.hasText(category)) {
        return switch (category) {
            case "grooming"   -> "미용";           // "동물미용" → "미용"
            case "hospital"   -> "동물병원";
            case "pharmacy"   -> "동물약국";
            case "cafe"       -> "카페";           // "cafe" → "카페"
            case "restaurant" -> "식당";           // "restaurant" → "식당"
            case "pension"    -> "펜션";           // "pension" → "펜션"
            case "boarding"   -> "위탁관리";       // "boarding" → "위탁관리"
            case "hotel"      -> "호텔";           // "hotel" → "호텔"
            case "supplies"   -> "반려동물용품";   // "supplies" → "반려동물용품"
            default -> category;
        };
    }
    return "HOSPITAL".equals(type) ? "동물병원" : "반려동물 시설";
}
```

> 주의: 이 수정 이전에 PET_DATA_API로 이미 적재된 데이터가 있다면
> 기존 English category 값을 일괄 업데이트하는 마이그레이션 SQL이 필요하다.
> `UPDATE locationservice SET category3 = '카페' WHERE category3 = 'cafe' AND data_source = 'PET_DATA_API';` 패턴으로.

---

## 3. 코드 품질 개선 (선택적)

### 3.1 `buildNameAliases()` — 지점명 처리 추가

**파일:** `RecommendService.java:332`

현재 suffix 목록에 지점 패턴이 없어서 "해피독 강남점"과 blog의 "해피독"이 매칭 실패할 수 있다.

추가 제안:
```java
suffixes.put("grooming", List.of(
    "미용", "애견미용", "반려동물미용", "애견미용실",
    "강남점", "서초점", "마포점", "홍대점", "신촌점",   // 지점 패턴
    "1호점", "2호점", "3호점"
));
```

또는 정규식 기반으로 "점" 앞에 지명 패턴을 범용 처리:
```java
// 지점명 suffix 제거: "강남점", "홍대점" 등
String stripped = name.replaceAll("[가-힣]{1,4}점$", "").trim();
if (stripped.length() >= 2) aliases.add(stripped);
```

**우선순위:** 낮음. 현재 fuzzy matching이 exact name match로 충분히 동작하는 경우가 많다.

### 3.2 `FacilitySyncService` — boarding/hotel 중복 체크 개선

현재 중복 체크: `existsByNameAndAddress(name, address)`

pet-data-api가 road_address와 jibun address 양쪽을 줄 수 있어서 같은 시설이 다른 주소 문자열로 들어올 수 있다.

개선 제안:
```java
// 위도/경도 기반 중복 체크 (반경 50m 이내 동명 시설은 동일로 간주)
locationServiceRepository.existsByNameAndNearLocation(name, lat, lng, 50.0)
```

**우선순위:** 낮음. 데이터 규모가 작을 때는 name+address 중복 체크로 충분.

---

## 4. 변경 불필요 확인

아래 코드는 이미 올바르게 구현돼 있다. 건드리지 않아도 된다.

| 코드 | 상태 |
|---|---|
| `FacilitySyncScheduler` (01:00 daily) | 완성 — pet-data-api endpoint만 열리면 동작 |
| `mergeNearbyCandidates()` scoring | 완성 — distanceScore 0.55 + ratingScore 0.20 + reviewScore 0.15 + popularityScore 0.10 |
| `LocationServiceService.searchLocationServicesByLocation()` | 완성 — ST_Within + ST_Distance_Sphere |
| `LocationServiceScoreScheduler` (00:00 daily) | 완성 — rating·reviewCount 기반 score 재계산 |
| `PetDataApiClient.fetchPopular()` / `fetchTrends()` | 완성 — GET /popular, GET /trends 호출 |

---

## 5. 전환 체크리스트

```
☑ pet-data-api GET /facilities 구현 완료 확인
☑ FacilitySyncService.categoryLabel() 9개 context 한국어 라벨 수정
   → grooming: 미용, cafe: 카페, restaurant: 식당, pension: 펜션,
      boarding: 위탁관리, hotel: 호텔, supplies: 반려동물용품
□ FacilitySyncService 수동 트리거 후 DB boarding/hotel 데이터 확인
   → SELECT count(*) FROM locationservice WHERE category3 IN ('위탁관리', '호텔') AND data_source = 'PET_DATA_API';
□ 주요 도시 반경 검색 테스트 (boarding/hotel context)
   → 후보 5개 이상 나오면 PETORY_OWNED_CONTEXTS 편입
□ PETORY_OWNED_CONTEXTS에 boarding, hotel 추가
□ 통합 테스트: RecommendService.recommend() boarding/hotel context로 호출
```

---

## 6. 참고 파일 위치 (Petory 백엔드)

| 파일 | 경로 |
|---|---|
| RecommendService | `backend/main/.../domain/recommendation/service/RecommendService.java` |
| FacilitySyncService | `backend/main/.../domain/location/service/FacilitySyncService.java` |
| FacilitySyncScheduler | `backend/main/.../domain/location/service/FacilitySyncScheduler.java` |
| PetDataApiClient | `backend/main/.../domain/recommendation/client/PetDataApiClient.java` |
| LocationService entity | `backend/main/.../domain/location/entity/LocationService.java` |
