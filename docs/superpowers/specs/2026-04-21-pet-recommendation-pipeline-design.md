# 반려동물 추천 파이프라인 설계

**날짜**: 2026-04-21  
**상태**: 승인됨  
**연관 프로젝트**: pet-data-api (Python/FastAPI), Petory (Java/Spring Boot)

---

## 목표

Petory 사용자가 미용실·병원을 찾거나 간식·사료·옷을 보고 있을 때, pet-data-api가 주변 공인 시설 데이터 + 네이버 블로그 트렌드 키워드 + LLM(Ollama llama3)을 종합해 개인화 추천을 반환한다.

---

## 아키텍처

```
Petory 프론트엔드
  ├── 현재 페이지 감지 (grooming / hospital / snack / food / clothes)
  ├── 브라우저 GPS로 lat/lng 획득
  └── Petory 백엔드 호출

Petory 백엔드 (Java/Spring)
  ├── Pet 테이블 조회 (반려동물 있으면 포함, 없으면 null)
  └── POST http://localhost:8000/recommend  { lat, lng, context, pet? }
        X-API-Key: <일반 키>

pet-data-api (Python/FastAPI)
  ├── PostgreSQL: 반경 내 공인 시설 조회 (context 타입 필터)
  ├── Redis: 해당 카테고리 트렌드 키워드 Top 10
  ├── Ollama llama3 (로컬): 시설 + 트렌드 + 펫 정보 → 추천문 생성
  └── JSON 응답 반환

Petory 프론트엔드
  └── 추천 카드 표시
```

---

## API 명세

### `POST /recommend`

**인증**: `X-API-Key` 헤더 (일반 키 권한)

**요청 바디**

```json
{
  "lat": 37.5665,
  "lng": 126.9780,
  "context": "grooming",
  "radius_km": 3,
  "top_n": 5,
  "pet": {
    "type": "dog",
    "breed": "말티즈",
    "age_months": 24
  }
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `lat` | float | ✅ | 사용자 위도 |
| `lng` | float | ✅ | 사용자 경도 |
| `context` | string | ✅ | `grooming` \| `hospital` \| `snack` \| `food` \| `clothes` |
| `radius_km` | float | ❌ | 검색 반경 (기본값: 3) |
| `top_n` | int | ❌ | 반환 시설 수 (기본값: 5) |
| `pet` | object | ❌ | 반려동물 정보 (없으면 null) |

**context → 시설 타입 매핑**

| context | 조회 시설 타입 | Redis 카테고리 |
|---------|--------------|--------------|
| `grooming` | 동물미용업 | `grooming` |
| `hospital` | 동물병원 | `hospital` |
| `snack` | — (시설 없음) | `snack` |
| `food` | — (시설 없음) | `food` |
| `clothes` | — (시설 없음) | `clothes` |

**응답 바디**

```json
{
  "context": "grooming",
  "facilities": [
    {
      "name": "해피독 미용실",
      "distance_m": 320,
      "address": "서울시 마포구 ..."
    }
  ],
  "trends": [
    { "keyword": "스포팅컷", "score": 41 },
    { "keyword": "여름컷", "score": 35 }
  ],
  "recommendation": "말티즈에게는 요즘 스포팅컷이 인기입니다. 근처 해피독 미용실이 320m 거리로 가장 가깝고...",
  "generated_at": "2026-04-21T10:00:00+09:00"
}
```

`recommendation`은 Ollama 실패 시 `null` 반환. 시설/트렌드 데이터는 항상 반환.

---

## 전제 조건: 시설 좌표 데이터

현재 `PetFacility` 모델에 `lat`/`lng` 컬럼이 없어 반경 검색이 불가능하다.  
수집 파이프라인에서 주소 → 좌표 변환(지오코딩)을 추가하고 `pet_facilities` 테이블에 컬럼을 추가한다.

- **지오코딩 API**: Kakao 로컬 API (무료 티어) 또는 OpenStreetMap Nominatim (무료, rate limit 있음)
- **처리 방식**: 수집 시 주소로 좌표 요청 → `lat`, `lng` 저장. 실패 시 `NULL` 허용
- **거리 계산**: PostgreSQL에서 Haversine 공식 적용 (`earth_distance` 또는 직접 수식)
- **NULL 시설 fallback**: 좌표 없는 시설은 지역(region_city/region_district) 기반 필터로 대체

---

## pet-data-api 구현 범위

### 신규 파일

| 파일 | 역할 |
|------|------|
| `app/api/recommend.py` | `/recommend` 라우터 |
| `app/schemas/recommend.py` | 요청/응답 Pydantic 스키마 |
| `app/recommender/llm.py` | Ollama 호출 클라이언트 |
| `app/recommender/builder.py` | 프롬프트 생성 로직 |
| `app/collector/geocoder.py` | 주소 → 좌표 변환 (Kakao/Nominatim) |

### 기존 파일 수정

| 파일 | 변경 내용 |
|------|----------|
| `app/main.py` | `/recommend` 라우터 등록 |
| `app/core/config.py` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `KAKAO_REST_API_KEY` 환경변수 추가 |
| `app/models/facility.py` | `lat`, `lng` 컬럼 추가 |
| `migrations/` | `lat`/`lng` 컬럼 추가 ALTER TABLE |
| `.env.example` | 신규 환경변수 항목 추가 |

### 신규 환경변수

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
KAKAO_REST_API_KEY=<카카오 REST API 키>  # 지오코딩용, 무료
```

---

## Ollama 프롬프트 구조

```
[시스템]
너는 반려동물 전문 추천 어시스턴트야. 반드시 한국어로, 3문장 이내로 간결하게 추천해.

[유저]
- 반려동물: {breed}, {age}살, {type} (없으면 생략)
- 찾는 서비스: {context_label}
- 주변 시설 (가까운 순): {시설명(거리m)} ...  (없으면 "주변 시설 정보 없음")
- 요즘 인기 키워드: {keyword1}, {keyword2}, ...

추천해줘.
```

---

## 에러 처리

| 상황 | 처리 방식 |
|------|----------|
| Ollama 다운 / 타임아웃 | `recommendation: null` 로 데이터만 반환 |
| 반경 내 시설 없음 | `facilities: []` + 트렌드만으로 프롬프트 구성 |
| Redis 연결 실패 | `trends: []` + 503 대신 빈 배열로 graceful 처리 |
| pet-data-api 자체 장애 | Petory가 try-catch → 추천 없이 기본 화면 표시 |

---

## Petory 구현 범위

### 신규 파일

| 파일 | 역할 |
|------|------|
| `PetDataApiClient.java` | pet-data-api HTTP 클라이언트 (RestClient) |
| `RecommendRequest.java` | 요청 DTO |
| `RecommendResponse.java` | 응답 DTO |
| `RecommendService.java` | Pet 조회 + 클라이언트 호출 조합 |
| `RecommendController.java` | `/api/recommend` 엔드포인트 |

### 설정 추가 (application.properties)

```properties
pet-data-api.base-url=http://localhost:8000
pet-data-api.api-key=${PET_DATA_API_KEY}
```

### 프론트엔드 (React)

- 페이지 context 감지 → 백엔드 `/api/recommend` 호출
- `navigator.geolocation.getCurrentPosition` 으로 GPS 획득
- 추천 카드 컴포넌트 표시 (`recommendation` null 이면 카드 숨김)

---

## 구현 순서

1. **pet-data-api**: `PetFacility`에 `lat`/`lng` 추가 + 지오코더 구현 + 마이그레이션
2. **pet-data-api**: Pydantic 스키마 + 반경 기반 시설 쿼리 로직
3. **pet-data-api**: Ollama 클라이언트 + 프롬프트 빌더
4. **pet-data-api**: `/recommend` 라우터 조합 + 테스트
5. **Petory**: `PetDataApiClient` + DTO + `RecommendService`
6. **Petory**: `RecommendController` + 프론트엔드 연동

---

## 비고

- 배포 시 Ollama → Claude API / OpenAI 교체 가능하도록 `LLMClient` 인터페이스로 추상화
- `snack` / `food` / `clothes` context는 시설 데이터 없이 트렌드만으로 추천 생성
- Petory의 LocationService 테이블은 반려동물 시설(사업자 등록)이므로 pet-data-api의 공공데이터 시설과 중복 없음 — 별도 운영
