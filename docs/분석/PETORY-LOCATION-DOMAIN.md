# Petory — location 도메인

> 파일: `backend/main/java/com/linkup/Petory/domain/location/`

## 역할

반려동물 관련 시설(동물병원·미용·카페 등)의 **저장·검색·리뷰·데이터 적재**를 담당한다.
앱 전체에서 시설 데이터의 단일 읽기 원천(SSOT)이 되며, recommendation 도메인이 이 DB를 직접 조회한다.

---

## 주요 클래스

### Entity

**`LocationService`** (`entity/LocationService.java`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `idx` | Long (PK) | auto increment |
| `name` | String(150) | 시설명 |
| `category1/2/3` | String(100) | 대/중/소분류 |
| `sido`, `sigungu`, `eupmyeondong`, `roadName` | String | 주소 계층 |
| `address` | String(255) | 전체 주소 (도로명 우선) |
| `latitude`, `longitude` | Double | 좌표 |
| `petFriendly` | Boolean | 반려동물 동반 가능 여부 |
| `dataSource` | String(50) | `"PUBLIC"` / `"BATCH_IMPORT"` |
| `rating` | Double | 리뷰 평점 (기본 0.0) |
| `reviewCount` | Integer | soft-delete 제외 리뷰 수 캐시 |
| `score` | Double | 종합 점수 (기본 0.0) |
| `isDeleted`, `deletedAt` | Boolean / LocalDateTime | Soft Delete |

공간 컬럼: DB에 `location` POINT(SRID 4326) 존재. 엔티티에 매핑하지 않고 네이티브 쿼리 `ST_Distance_Sphere`로 반경 검색.

---

### Service

**`LocationServiceService`** — 핵심 검색 서비스

검색 우선순위 (단일 메서드 `searchLocationServices`):

1. **위치(lat·lng·radius)** 있음 → `findByRadius` (ST_Distance_Sphere)
2. **지역(sido/sigungu/eupmyeondong/roadName)** 있음 → 계층별 조회
3. **keyword만** 있음 → FULLTEXT 전국 검색 (fallback)
4. 아무것도 없음 → 전체 평점순

`sort` 파라미터: `distance` / `rating` / `reviews` / `score`. `score`는 쿼리 후 post-sort.

**`LocationImportService`** — Python batch JSON 적재

```
importFromStream(InputStream) / importFromFile(String)
  → objectMapper.readValue → List<LocationImportDto>
  → processEntries()
      isValid(): name·address 비어있으면 skip, lat·lng null이면 skip, status="폐업"이면 skip
      existsByNameAndAddress(): 중복이면 duplicate++
      toEntity(): category3에 한글 카테고리 레이블, dataSource="BATCH_IMPORT", petFriendly=true
      batchWriter.saveBatch(batch) (batchSize=500, @Transactional(REQUIRES_NEW))
  → SyncResult(total, saved, duplicate, skipped)
```

**`LocationServiceBatchWriter`** — `@Transactional(REQUIRES_NEW)` 단위로 배치 저장.

**`FacilitySyncScheduler`** — 매일 01:00 cron. `app.location.import.file-path` 미설정이면 skip.

**`LocationServiceAdminService`** — 공공데이터 CSV 수동 적재 등 관리 기능.

**`NaverMapService`** — 주소 → 좌표 변환 (Naver Maps Geocoding API).

**`PublicDataLocationService`** — 공공데이터포털 API 연동 적재.

---

### Repository

`LocationServiceRepository` (도메인 인터페이스) → `JpaLocationServiceAdapter` (JPA 구현체)

주요 메서드:

| 메서드 | 설명 |
|---|---|
| `findByRadius(lat, lng, radiusM, keyword, category, sort)` | ST_Distance_Sphere 반경 검색 |
| `findBySido/Sigungu/Eupmyeondong/RoadName(...)` | 지역 계층별 조회 |
| `findByNameContaining(keyword, category)` | FULLTEXT 키워드 검색 |
| `existsByNameAndAddress(name, address)` | 중복 체크 (import 시 사용) |
| `findTop10ByCategoryOrderByRatingDesc(category)` | 카테고리별 인기 상위 10개 |

---

### Controller

**`LocationServiceController`** (`GET /api/location-services/search`, `DELETE /api/location-services/{idx}`)

쿼리 파라미터: `latitude`, `longitude`, `radius`, `sido`, `sigungu`, `eupmyeondong`, `roadName`, `category`, `keyword`, `sort`, `size` (기본 100)

**`LocationServiceAdminController`** (`POST /api/admin/location/import`)

- `@PreAuthorize("hasAnyRole('ADMIN', 'MASTER')")`
- `multipart/form-data` 파일 수신 → `locationImportService.importFromStream()`
- 응답: `{total, saved, duplicate, skipped}`

**`LocationServiceReviewController`** — 리뷰 CRUD

**`GeocodingController`** — 주소 → 좌표 변환 API

---

## 데이터 적재 경로

| 경로 | 트리거 | 서비스 |
|---|---|---|
| Python batch CLI → JSON 파일 | cron/GitHub Actions + Spring cron 01:00 | `LocationImportService.importFromFile` |
| Admin multipart 업로드 | 관리자 수동 | `LocationImportService.importFromStream` |
| 공공데이터 API | 수동 | `PublicDataLocationService` |

---

## LocationImportDto

Python batch CLI 출력 JSON의 스키마:

```java
// LocationImportDto.java
String name;       // 시설명 (필수)
String category;   // grooming|hospital|pharmacy|cafe|restaurant|pension|boarding|hotel|supplies
String address;    // 전체 주소 (필수)
String sido;       // 시도
String sigungu;    // 시군구
Double lat;        // 위도 (필수)
Double lng;        // 경도 (필수)
String phone;
String status;     // "폐업" 이면 skip
```

---

## category 매핑 (ImportService)

| Python key | DB category3 |
|---|---|
| grooming | 미용 |
| hospital | 동물병원 |
| pharmacy | 동물약국 |
| cafe | 카페 |
| restaurant | 식당 |
| pension | 펜션 |
| boarding | 위탁관리 |
| hotel | 호텔 |
| supplies | 반려동물용품 |
