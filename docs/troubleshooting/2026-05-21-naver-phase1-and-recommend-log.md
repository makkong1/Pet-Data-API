# 작업 결과 및 문제점: 네이버 블로그 Phase 1 + 추천 API 로그 분석

**일시:** 2026-05-21  
**작업자:** makkong1  
**대상 브랜치:** `dev`

---

## 1. 완료된 작업 요약

### 네이버 블로그 트렌드 수집 Phase 1

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| sort | `sim` 고정 | `sim` + `date` 이중 수집 |
| 병렬화 | 순차 `await` | `asyncio.gather` + 동적 세마포어 |
| 중복 제거 | 없음 | `link` 기준 seen-set dedup |
| blogger 필드 | drop | `blogger_name`, `blogger_link` 보존 |
| 동시 호출 상한 | 무제한 | `max(1, min(8, len(queries)*2))` |

**변경 파일:**
- `app/ingestion/naver.py`
- `tests/test_naver_collector.py`

**테스트 결과:** 8/8 PASSED

```
tests/test_naver_collector.py::test_search_naver_blog_returns_items PASSED
tests/test_naver_collector.py::test_collect_category_trends_merges_queries PASSED
tests/test_naver_collector.py::test_collect_category_trends_calls_both_sorts PASSED
tests/test_naver_collector.py::test_collect_category_trends_deduplicates_by_link PASSED
tests/test_naver_collector.py::test_collect_category_trends_logs_warning_on_fetch_error PASSED
tests/test_naver_collector.py::test_category_keywords_has_required_categories PASSED
tests/test_naver_collector.py::test_search_naver_blog_passes_sort_to_params PASSED
tests/test_naver_collector.py::test_search_naver_blog_includes_blogger_fields PASSED

8 passed in 0.08s
```

---

## 2. 추천 API 로그 분석 (grooming 컨텍스트)

**테스트 요청:** `lat=37.60950, lng=127.07735, radius_km=10.0, top_n=5`

### 정상 동작 확인

- public_db → 20개 후보 → top 5 반환 흐름 정상
- score 순위 3회 요청 내내 일관
- kakao 캐시 작동 확인: 1차 390ms → 2·3차 9ms

**레이턴시 상세:**

| 요청 | total | blog | kakao | rank |
|------|-------|------|-------|------|
| 1차 (cold) | 930ms | 439ms | 390ms | 31ms |
| 2차 | 220ms | 196ms | 9ms | 2ms |
| 3차 | 476ms | 443ms | 9ms | 2ms |

---

## 3. 발견된 문제점

### ✅ P1 — 꾸러미세상 distance 불일치 (해결 2026-05-22)

**현상:**

| 요청 | distance_m | address |
|------|-----------|---------|
| 1차 | 409 | (없음) |
| 2·3차 | 1110 | 서울 중랑구 봉화산로 115 |

동일한 좌표(lat/lng 동일)로 3번 요청했는데 같은 시설의 거리가 달라짐.

**근본 원인:**

`rank_grooming_facilities` step 3 dedup이 `_normalize_for_match` 결과를 **exact string** 비교했기 때문.

- 공공 DB: `"꾸러미세상"` (409m, address 없음)
- Kakao 검색 결과: `"꾸러미세상 애견용품"` (1110m, 도로명 주소 있음)
- `_is_same_facility`(step 2): `fuzz.ratio("꾸러미세상", "꾸러미세상애견용품")` ≈ 71% < threshold 85% → merge 실패 → Kakao standalone 추가
- step 3 dedup: `"꾸러미세상"` ≠ `"꾸러미세상애견용품"` (exact) → 둘 다 생존 → top-5에 동일 업장 2개 노출

1차 요청에서 blog extraction이 "꾸러미세상"을 mention_map에 포함시키지 않으면 Kakao 미호출 → public 단독 409m 반환. 2·3차에서 mention 있어 Kakao 호출 → 중복 엔트리 발생.

**수정 내용 (`grooming_ranker.py`):**

1. `_might_be_same_facility` 함수 추가:
   - 짧은 쪽(≥3자)이 긴 쪽에 포함되거나(`shorter in longer`) fuzz.ratio ≥ 85이면 True
   - "꾸러미세상" in "꾸러미세상애견용품" → True ✓
2. step 3 dedup을 exact 비교 → `_might_be_same_facility` 로 교체
3. `public_matched=True` 엔트리 우선 보존 (공공 데이터 우선)

**커밋:** `a62b068` feat: fix(ranker): 공공 약식명 vs Kakao 정식명 dedup 누락 수정

**테스트:** `test_rank_dedup_public_name_kakao_longer_name` (P1 재현 시나리오) 포함 13/13 통과

**재발 방지:** step 2 merge에는 보수적인 `_is_same_facility`(ratio≥85)를 유지하고, dedup에만 광의 판단 적용. Kakao 정식명이 공공 DB 약식명보다 길어지는 패턴에 대해 substring 포함 여부로 추가 포착.

---

### 🟡 P2 — `trends: []` (트렌드 데이터 없음)

**현상:** 3회 요청 전부 `"trends":[]` 반환.

**추정 원인:**
- 트렌드 수집 스케줄(매일 03:00)이 아직 실행되지 않음
- Redis grooming 키가 비어 있음

**확인 필요:**
```bash
redis-cli GET "trend:grooming"
```

Phase 1 작업으로 `sim`+`date` 이중 수집이 적용됐으므로 다음 스케줄 실행 후 trends 필드가 채워지는지 검증 필요.

---

### 🟡 P3 — mention_count 상위 4개 전부 6으로 동일

**현상:**
```
니니 애견 미용실:     mention_count=6, mention_score=1.0
꾸러미세상:           mention_count=6, mention_score=1.0
두유네 애견미용실:    mention_count=6, mention_score=1.0
멍미용:               mention_count=6, mention_score=1.0
최덕황애견미용학원:   mention_count=2, mention_score=0.3333
```

mention_score가 1.0으로 포화되어 상위 4개 간 실질적인 분별력이 없음. 최종 score 차이는 거리에서만 발생.

**추정 원인:**
- 현재 쿼리 수 적음(sim 단일 수집) → 언급 카운트 최대치가 낮음
- Phase 1 이후 sim+date 이중 수집 적용 시 카운트 분포가 바뀔 수 있음

**확인 필요:** Phase 1 수집 스케줄 실행 후 mention_count 분포 재관찰.

---

### 🟢 P4 — blog 레이턴시 불안정 (세마포어 설계 주의사항)

**현상:** blog latency가 196ms ~ 443ms로 편차 큼. kakao는 캐시 후 9ms로 안정.

**원인:** Redis 블로그 언급 캐시 TTL 또는 캐시 키 구조에 따라 cold/warm 차이 발생.

**Phase 1 주의사항 (코드 리뷰에서 지적됨):**
현재 세마포어 공식 `max(1, min(8, len(queries)*2))`은 현재 카테고리 기준(최대 쿼리 3개)에서 `sem_limit == task 수`가 되어 실질적 throttle이 없음. 쿼리가 5개 이상으로 늘어나는 시점에 자동 상한 작동. 필요 시 고정값(`asyncio.Semaphore(4)`)으로 교체 고려.

---

## 4. 다음 액션

| 우선순위 | 항목 | 작업 | 상태 |
|---------|------|------|------|
| P1 | 꾸러미세상 distance 불일치 | dedup 로직 수정 (`a62b068`) | ✅ 완료 |
| P2 | trends 빈 배열 | 다음 스케줄 후 Redis 키 확인 | ⏳ 대기 |
| P3 | mention_count 포화 | Phase 1 수집 후 분포 재관찰, 필요 시 쿼리 확장(6순위) | ⏳ 대기 |
| P4 | 세마포어 throttle 없음 | 쿼리 확장 시 고정 상한으로 교체 검토 | ⏳ 대기 |

---

## 5. Phase 2 예정 작업 (별도 사이클)

- `intent` 메타데이터 + `BlogTrendRawItem` 타입 계약
- `quality_score` / 광고 노이즈 필터
- `CATEGORY_KEYWORDS` 질의 확장 (6순위)

관련 스펙: `docs/superpowers/specs/2026-05-21-naver-blog-trend-phase1-design.md`
