# 운영 로그 분석: POST /recommend grooming 실제 호출 관찰

**일시:** 2026-05-22  
**대상 브랜치:** `dev`  
**계기:** Petory 서버에서 실제 요청 수신 후 로그 최초 관찰

---

## 관찰 조건

- 요청 파라미터: `context=grooming`, `lat=37.60952`, `lng=127.07754`, `radius_km=10.0`, `top_n=5`
- `pet`: `{type: dog, breed: 강아지, age_months: 5}`
- `GROOMING_MVP_ENABLED=true` → context_pipe(grooming-mvp-v1) 경로

---

## 관찰 1 — Petory가 동일 파라미터로 1초 내 3회 호출 🔴

```
[6a08a73698e34220]  12:08:34.015  200 OK
[2a99aff93792492f]  12:08:34.495  200 OK  (+0.48s)
[3c690d7167c54c63]  12:08:34.724  200 OK  (+0.71s)
```

세 요청 모두 동일 파라미터, 모두 200 반환. 재시도가 아니라 **중복 발송**에 가깝다.

**가능한 원인**
- Petory 클라이언트 타임아웃이 짧아서 응답 수신 전에 재시도를 트리거
- 비동기 병렬 호출 코드에서 중복 dispatch
- Petory 내부 retry 정책이 200에도 재시도하도록 잘못 설정

**조치 방향**
- Petory 쪽에서 request_id 기반 중복 제거 또는 debounce 추가
- 파이썬 서버 쪽에서 단기 응답 캐시(`request_id` 또는 파라미터 해시 기준, TTL 2s)로 방어 가능하나 클라이언트 수정이 우선

---

## 관찰 2 — Kakao Redis 캐시 효과 정상 동작 ✅

| 요청 | blog | kakao | total |
|------|------|-------|-------|
| 1번 (6a08a7) | 431ms | 383ms | **889ms** |
| 2번 (2a99af) | 394ms | **37ms** | 449ms |
| 3번 (3c690d) | 196ms | **6ms** | 211ms |

- kakao: 383ms → 37ms → 6ms. 1번 이후 Redis TTL 캐시 히트.
- blog: 431ms → 394ms → 196ms. 네이버 API 응답 자체가 빨라지거나 세마포어 대기 없이 통과.
- 3번 총 latency 211ms는 캐시 완전 활용 시 기대치와 부합.

---

## 관찰 3 — "우솔동물병원"이 grooming 결과에 포함 🟠

```json
{"name": "우솔동물병원", "source": "public", "score": 0.3623, "reasons": ["distance"]}
```

`reasons`에 `distance` 하나만 있음 — mention·trend_match 없이 반경 안에 있다는 이유만으로 상위 5개에 포함.

**원인**  
공공 DB `pet_facilities.type`이 `HOSPITAL`인 시설이 `grooming` 컨텍스트 반경 쿼리에서 걸러지지 않음.  
`get_nearby_facilities`의 `context→type` 필터가 grooming에 대해 HOSPITAL을 명시적으로 제외하지 않는 것으로 추정.

**조치 방향**  
- `get_nearby_facilities`에서 `context=grooming`일 때 `type != 'HOSPITAL'` 조건 추가
- 또는 grooming 전용 `CONTEXT_TO_FACILITY_TYPE` 매핑을 `BUSINESS`로 제한

---

## 관찰 4 — "니니 애견 미용실" mention_count=0 🟠

```json
{"name": "니니 애견 미용실", "mention_count": 0, "source": "public", "score": 0.5144}
```

Phase 2a에서 `"니니 애견 미용실"` 텍스트에서 `"니니"`를 추출하도록 suffix bridge 패턴을 수정했다.  
그런데 블로그에서 뽑힌 후보명 `"니니"` 와 공공 DB 시설명 `"니니 애견 미용실"` 사이 매핑이 이루어지지 않음.

**구조적 원인**  
`grooming_ranker`의 mention 매핑 로직이 **완전 일치(exact)** 또는 **포함(substring)** 기준인데,  
`"니니 애견 미용실".contains("니니")` 는 참이지만 `"니니"` 가 너무 짧아 신뢰도가 낮거나, 역방향(`mention_map["니니"]` 가 시설명과 매핑되는 로직)이 없는 것으로 보임.

**조치 방향**  
- `grooming_ranker`에서 시설명 → 후보명 fuzzy 매핑 추가 (시설명이 후보명을 포함하거나, 후보명이 시설명에 포함되는 경우)
- 단, 너무 짧은 후보명(2-3자)은 오매핑 위험 있으므로 최소 길이 임계치(4자 이상 권장) 적용

---

## 관찰 5 — candidate_raw 상시 20 포화 🟡

```
candidate_raw=20 after_cap=20  (3번 모두)
```

`_CANDIDATE_CAP=20` 한도를 매 요청마다 꽉 채움.  
Phase 2a로 파편이 줄었다면 유효 후보 밀도는 높아졌을 것이나,  
실제로 20개 전부가 실존 업장인지 아직 확인 안 됨.

**조치 방향**  
- 실제 mention_map 키 목록을 한 번 덤프해서 유효 상호명 vs 노이즈 비율 측정
- 필요 시 `_CANDIDATE_CAP`을 높이거나 `_MIN_MENTION_COUNT` 기준을 올려 품질 필터링 강화

---

## 관찰 6 — recommend response 전체 JSON 로그 🟡

```python
_log.info("recommend response: %s", response.model_dump_json())
```

주소·위도·경도 포함 전체 응답이 로그에 찍힘.  
개발 중에는 유용하나 운영 시 로그 크기 및 개인정보(주소) 노출 문제.

**조치 방향**  
운영 전 아래처럼 요약 로그로 교체:
```python
_log.info(
    "[%s] recommend response facilities=%d recommendation_len=%s version=%s",
    request_id, len(facilities), len(recommendation or ""), recommend_version,
)
```

---

## 관찰 7 — 로그 인터리빙 (정상 동작, 주의 필요) ℹ️

```
[2a99af] context_pipe ... public_db count=20
[6a08a7] recommend_copy ...                    ← 다른 요청 로그 삽입
[2a99af] context_pipe ... summary ...
```

비동기 처리 특성상 발생. `[rid]` 기준 grep으로 추적 가능.  
운영 규모가 커지면 Loki/Elasticsearch 같은 로그 집계 툴에서 `request_id` 필드로 필터링.

---

## 우선순위 요약

| # | 이슈 | 심각도 | 조치 대상 |
|---|------|--------|-----------|
| 1 | Petory 3중 중복 호출 | 🔴 High | Petory 클라이언트 |
| 2 | 동물병원이 grooming 결과에 포함 | 🟠 Medium | `get_nearby_facilities` 타입 필터 |
| 3 | 니니 mention 매핑 누락 | 🟠 Medium | `grooming_ranker` fuzzy 매핑 |
| 4 | candidate_raw 상시 포화 | 🟡 Low | 품질 측정 후 판단 |
| 5 | response 전체 JSON 로그 | 🟡 Low | 운영 전 교체 |
| 6 | 로그 인터리빙 | ℹ️ Info | 현재 구조상 정상 |
