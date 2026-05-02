# Petory 카테고리 추천 재설계 스펙 (Python 서버)

**작성일:** 2026-05-01  
**상태:** Draft (구현 전 설계)  
**대상:** `pet-data-api` 단독 범위 (Petory Java 서버 변경 제외)

---

## 1) 배경과 문제 정의

사용자 기대 플로우:

1. Petory에서 카테고리(`미용`, `병원`, `용품점`) 클릭
2. Python 서버가 카테고리에 맞는 **주변 서비스 + 최근 트렌드**를 반환
3. Ollama가 해당 데이터 기반으로 추천 문장을 생성

현재 서버의 실제 동작과의 갭:

- `grooming`, `hospital`만 주변 시설 조회 가능
- `snack`, `food`, `clothes`는 시설 조회가 구조적으로 비활성화
- 트렌드는 카테고리 전체 키워드 빈도이며, 지역/시설 인기와 직접 연결되지 않음
- 수동 트리거는 공공데이터 수집만 수행하고 트렌드 수집은 별도

즉, 현재는 "카테고리별 주변 서비스 추천"이 아니라 "일부 카테고리의 근거리 시설 + 일반 키워드" 수준이다.

---

## 2) 목표

### 기능 목표

- 카테고리별 추천을 `서비스형`과 `상품형`으로 분리해 일관되게 지원
- `미용/병원/용품점`은 모두 주변 후보 목록을 반환
- 네이버 블로그 데이터로 카테고리별 트렌드 신호를 만들고 추천에 반영
- Ollama는 항상 구조화된 입력(후보/점수/트렌드)을 받아 최종 요약만 담당

### 품질 목표

- 카테고리 클릭 후 추천 API 응답 p95 3초 이내 (LLM 제외 시 800ms 이내)
- 데이터 갱신 실패 시 직전 캐시를 유지해 503 빈도를 낮춤
- 추천 결과에 근거 데이터(거리, 트렌드 점수, 갱신시각)를 포함

---

## 3) 비목표 (이번 설계 범위 밖)

- Petory Java 서버 컨트롤러/프론트 UI 변경
- 유료 외부 LLM 도입
- 대규모 분산 처리 인프라(Kafka, Spark 등)

---

## 4) 카테고리 모델 재정의

기존 `snack/food/clothes` 대신, 사용자 기능 중심으로 다음 3개 1차 표준화:

- `grooming` (미용)
- `hospital` (병원)
- `supplies` (용품점)

하위 관심사(사료/간식/의류)는 `supplies`의 `subtopics`로 유지:

- `food`, `snack`, `clothes`

이렇게 분리하면 "용품점 주변 후보 + 요즘 관심 키워드"를 동시에 만들 수 있다.

---

## 5) 타겟 아키텍처

## 5.1 데이터 레이어

### A. 시설 마스터 (PostgreSQL)

- `pet_facilities` 유지
- `supplies` 카테고리용 시설 소스 추가 필요
  - 옵션 1: 공공 데이터에서 반려동물 판매/위탁/생산 업종 확장 수집
  - 옵션 2: 장소 API(네이버/카카오) 기반 보강 테이블 추가

### B. 트렌드 시그널 (Redis + PostgreSQL 선택)

- 기존 Redis Sorted Set 유지
- 카테고리 + 지역 단위 키 도입:
  - `trends:{category}:{region_key}:keywords`
  - `trends:{category}:{region_key}:updated_at`

`region_key` 예: `seoul_gangnam`, `global`

### C. 추천 피처 스냅샷 (선택)

- 디버깅용으로 추천 입력 스냅샷 저장 테이블 추가 권장
- 문제 발생 시 "왜 이 추천이 나왔는지" 추적 가능

---

## 5.2 수집 파이프라인

### 시설 수집 (18:05)

1. 공공 API 페이지네이션 수집
2. 업종 정규화 (`BUSINESS_GROOMING`, `HOSPITAL`, `SUPPLIES_STORE`)
3. 주소 지오코딩, 좌표 보강
4. upsert + 소스별 로그 기록

### 트렌드 수집 (18:00)

1. 카테고리별 쿼리 템플릿 + 지역 키워드 조합 생성
2. Naver Blog Search API 호출
3. 텍스트 정제 + 형태소 추출 + 불용어 필터
4. 키워드 점수 집계 후 Redis 저장

---

## 5.3 추천 엔진

추천 점수는 규칙 기반으로 먼저 계산하고, LLM은 요약만 수행:

`final_score = w1*distance_score + w2*trend_score + w3*freshness_score + w4*source_quality_score`

- `distance_score`: 사용자 거리 기반
- `trend_score`: 해당 카테고리/지역 트렌드 키워드 매칭 점수
- `freshness_score`: 최신 수집 데이터 가중치
- `source_quality_score`: 리뷰/언급량 등 보조 지표 (2단계)

LLM 프롬프트에는 상위 N개 후보와 각 후보 근거값만 전달한다.

---

## 6) API 재설계안 (Python 서버)

## 6.1 `POST /recommend` (기존 확장)

요청:

```json
{
  "lat": 37.56,
  "lng": 126.97,
  "category": "hospital",
  "region_hint": "seoul_gangnam",
  "radius_km": 3,
  "top_n": 5,
  "pet": {"type":"dog","breed":"말티즈","age":"2살"}
}
```

응답:

```json
{
  "category": "hospital",
  "updated_at": "2026-05-01T09:00:00Z",
  "candidates": [
    {
      "name": "A동물병원",
      "distance_m": 420,
      "score": 0.81,
      "score_breakdown": {
        "distance": 0.45,
        "trend": 0.23,
        "freshness": 0.08,
        "quality": 0.05
      }
    }
  ],
  "trends": [
    {"keyword":"야간진료","score":38},
    {"keyword":"중성화","score":24}
  ],
  "recommendation": "..."
}
```

## 6.2 `POST /collect/trigger`

관리자 수동 수집 범위를 분리:

- `scope=facilities`
- `scope=trends`
- `scope=all`

운영자가 "트렌드만 즉시 갱신" 가능해야 품질 회복이 빠르다.

## 6.3 `GET /trends/{category}`

- `region_key` 쿼리 지원 (`global` 기본)
- 결과에 `updated_at`, `source_count` 포함

---

## 7) 구현 단계 제안

### Phase 1 (필수)

- 카테고리 스키마 재정의 (`supplies` 도입)
- 트렌드 수집 scope 분리 및 수동 트리거 추가
- 추천 응답에 `candidates`, `score`, `updated_at` 포함
- 스케줄/문서/환경변수 정합성 정리

### Phase 2 (권장)

- `supplies` 시설 소스 확장 (공공 업종 또는 장소 API)
- 지역 단위 트렌드 키 설계 적용
- 추천 점수 가중치 튜닝

### Phase 3 (고도화)

- 추천 피처 로그 저장 + 오프라인 평가 지표(MRR, CTR proxy)
- Ollama 프롬프트 A/B 템플릿 운영

---

## 8) 파일 변경 가이드 (예상)

- `app/recommender/facilities.py`: 카테고리 매핑/점수 계산
- `app/api/recommend.py`: 응답 스키마 확장
- `app/schemas/recommend.py`: `candidates`, `score_breakdown` 추가
- `app/collector/naver.py`: 지역 키워드 기반 수집 함수
- `app/collector/runner.py`: `scope` 기반 트리거 분기
- `app/api/collect.py`: `scope` 파라미터 수용
- `app/cache/redis.py`: region_key 포함 키 스키마
- `tests/*`: 카테고리/점수/트리거 시나리오 테스트 추가

---

## 9) 수용 기준 (Acceptance Criteria)

- `grooming`, `hospital`, `supplies` 모두 추천 응답에서 `candidates`가 비어있지 않음(데이터 존재 지역 기준)
- `/collect/trigger?scope=trends` 실행 후 1분 이내 `/trends/{category}` 갱신시각 변경
- 추천 응답이 근거값(`distance_m`, `score_breakdown`)을 포함
- 트렌드 수집 실패 시 기존 캐시 유지 + 오류 로그 기록

---

## 10) 리스크와 대응

- **리스크:** 용품점 데이터 소스 품질 부족  
  - **대응:** 공공데이터 업종 확장 + 장소 API 보강 혼합

- **리스크:** 블로그 검색 결과 편향(광고/중복)  
  - **대응:** 도메인/문구 필터, 중복 제거, 불용어 사전 강화

- **리스크:** Ollama 응답 지연  
  - **대응:** 규칙 기반 top-1 추천 문장 템플릿 폴백 유지

---

## 11) 결론

현재 서버는 "근거리 시설 조회 API + 키워드 캐시" 단계다.  
본 재설계의 핵심은 **카테고리 모델 정리 + supplies 시설 소스 확보 + 점수 기반 추천 엔진화**이며, 이를 적용하면 Petory의 "카테고리 클릭형 추천 UX"와 맞는 형태로 동작한다.
