# Grooming Recommendation MVP (`POST /recommend`) — 현행 구현 명세

> **목적.** `context`가 특정 세트에 속하고 **`GROOMING_MVP_ENABLED=true`**일 때, 공공 반경 후보 위에 **블로그 멘션 + Kakao Local** 정보를 얹어 응답을 구성한다. 레거시 경로(공공 근처 시설 + 트렌드·선택적 LLM)와 분리된다.
> **동기화 기준 코드:** `app/serving/api/recommend.py`, `app/ingestion/grooming_blog.py`, `app/ingestion/kakao.py`, `app/serving/recommender/grooming_ranker.py`, `app/serving/recommender/ranker.py`

---

## 1. 활성 조건 및 범위 (중요)


| 항목                      | 내용                                                                                                                                                                                                                                                           |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **플래그**                 | `settings.GROOMING_MVP_ENABLED` (환경변수 `GROOMING_MVP_ENABLED`, 기본 `false`)                                                                                                                                                                                    |
| **적용 컨텍스트**             | `ENRICHED_CONTEXTS`에 포함된 모든 `context`에 동일 규칙 적용 (**그루밍 한정 아님**). 이름은 레거시이나 동작은 “멀티 컨텍스트 MVP”.                                                                                                                                                                |
| **컨텍스트 집합**             | `grooming`, `hospital`, `supplies`, `pharmacy`, `cafe`, `pension`, `restaurant`, `boarding`, `hotel` (`recommend.py` 상수와 동일)                                                                                                                                 |
| `**recommend_version`** | 조건 만족 시 `"{normalized_context}-mvp-v1"` (예: `grooming-mvp-v1`). 그 외 `legacy`.                                                                                                                                                                                |
| **레거시 분기**              | `GROOMING_MVP_ENABLED=false`이면 **항상** `legacy_pipe`(유효 `context`는 정규화 후 모두 `ENRICHED_CONTEXTS`에 속함). 레거시: 공공 `get_nearby` 위주·`FacilityItem` 직변환, `include_copy` 등에 따라 트렌드·선택적 LLM. MVP 경로와 달리 **멘션·`rank_grooming_facilities`·`rank_facilities` 신호 레이어 없음.** |


**Petory 호출 규격**은 변경 없음: `PetDataApiClient.recommend(lat, lng, context, ...)`. 현재 서버 기준 유효 `context`는 정규화 후 모두 **`ENRICHED_CONTEXTS`**에 들어가므로, `**GROOMING_MVP_ENABLED`만 켜면** MVP 파이프가 동작하고, 끄면 레거시로 떨어진다 (`docs/PETORY-INTEGRATION.md` 참고).

---

## 2. 파이프라인 순서 (`context_pipe`)

**용어 정리 (충돌 없음)**

- **서로 “다른 작업”이라고 했던 것**은 레포 경계 `INGESTION`(공공 API → PostgreSQL 적재·스케줄)과 `SERVING`(요청 시점 처리, 예: `POST /recommend`)을 가리킨다. 수집은 스케줄 타이머, 추천은 클라이언트 호출 한 번 단위. 자세히는 `[INGESTION-VS-SERVING.md](INGESTION-VS-SERVING.md)`.
- **한 흐름**은 `SERVING` **안에서만** 말한다. 같은 HTTP 요청을 처리할 때 `recommend()`가 **같은 `request_id`로** 로컬 DB 반경 조회 → 네이버 블로그 → Kakao → 병합·랭킹을 연속 호출한다. 근거(적재된 공공 데이터 vs 실시간 외부 API)만 다르고, 추천 응답을 만드는 **단일 오케스트레이션**이다.

아래 번호는 `SERVING` **파이프** 순서 (`app/serving/api/recommend.py` 요약).

1. **공공 근거(로컬 DB)** — `get_nearby_facilities`
  행안부 등으로 채워 둔 `pet_facilities` 반경 목록. `CONTEXT_TO_CATEGORY`·`CONTEXT_TO_FACILITY_TYPE` 필터, `top_n * 4`까지 조회 후 뒤에서 잘림.
2. **블로그 근거(외부 API)** — `extract_grooming_mentions` / `extract_context_mentions`
  네이버 블로그 검색으로 제목·요약에서 이름 후보·멘션 신호 확보 → `mention_map`, `candidate_names`(§3). 실패 시 빈 값으로도 파이프는 계속됨.
3. **카카오 근거(외부 API)** — `search_kakao_places`
  2단계에서 나온 `**candidate_names`만** 쿼리 입력 (`_build_query` + 접미사, `app/ingestion/kakao.py`). 실패 시 빈 맵.
4. `**rank_grooming_facilities`** — 위 세 근거를 **한 세트의 후보 dict**로 병합 (§5).
5. `**rank_facilities`** — 신호 가중합으로 최종 `**score`, `mention_score`, `signal_scores`, `reasons`** (§6); 병합 층의 임시 `score`는 여기서 **덮어씀**.
6. `**build_context_copy`** — 규칙 기반 카피; 응답 `FacilityItem`은 최종 랭커 반영.

**카테고리 키워드 문자열 추출**(예: `category_keywords_extract`)은 이 MVP 분기에서는 **호출되지 않는다**(타 모듈·향후 확장용일 수 있음).

**관측:** 같은 요청 안에서 `context_pipe` 접두 로그로 이어짐 (`mention_map … sample=`, `summary … latency_total` 등, `grep context_pipe`).

---

## 3. 블로그 멘션 추출 (`grooming_blog`)


| 항목                       | 내용                                                                                                                                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **에러 시**                 | `[]`로 폴백, 추천은 계속 진행                                                                                                                                                                                          |
| `**mention_map`**        | 이름별 `{count, freshness}` 집계. `count`는 **서로 다른 포스트(링크 등 식별자 기준)**에서 해당 이름 후보가 잡힌 횟수. 상한·컷 적용 후 상위만 `mention_map`/Kakao 입력에 반영.                                                                                |
| **형태소(kiwipiepy)**       | **미사용**. 제목·요약 문자열에서 정규식·차단 패턴 등 규칙 기반 추출 (**Phase 2a**; 결과·맥락은 `[docs/superpowers/results/2026-05-22-grooming-blog-phase2a-result.md](superpowers/results/2026-05-22-grooming-blog-phase2a-result.md)` 참고). |
| `**_MIN_MENTION_COUNT`** | 현재 코드 기본값 **2**. 위 `count`(유니크 포스트 수)가 이 미만이면 이름이 **후보에서 제외**.                                                                                                                                               |
| `**_CANDIDATE_CAP`**     | 현재 코드 기본값 **20**. 멘션 기반 이름 후보·Kakao 호출 진입 상한 근처.                                                                                                                                                             |


**품질·정확도**는 이름 인식 규칙에 좌우. 트러블슈팅 예: `[docs/troubleshooting/2026-05-22-petory-recommend-log-analysis.md](troubleshooting/2026-05-22-petory-recommend-log-analysis.md)`.

---

## 4. Kakao 호출 규격 (`kakao.py`)


| 항목                             | 값                                                                                                                                         |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **후보 문자열 상한 `_CANDIDATE_CAP`** | **20** (`search_kakao_places` 진입 전 `candidate_names[:20]`)                                                                                |
| **동시성 `_SEMAPHORE`**           | **5** (`asyncio.Semaphore`)                                                                                                               |
| **HTTP 호출당 결과 `size`**         | **5**, `sort=distance`, `radius=20000`(m)                                                                                                 |
| **캐시 TTL `_KAKAO_PLACE_TTL`**  | **600s**                                                                                                                                  |
| **캐시 키** (`_cache_key`)        | `kakao:place:{normalized_context}:{키워드_정규화명}:{격자좌표_lat}:{격자좌표_lng}` — 격자 좌표는 반올림 2자리(`_coord_grid`). 이름별 1키 → 후보 문자열 하나당 캐시/HTTP 쌍 최대 1회. |


**관측:** `INFO kakao_place [...] cache_hit/cache_miss/http_ok/http_err`

---

## 5. Grooming Ranker 병합 층 (`grooming_ranker.py`)


| 단계                            | 동작                                                                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **언급 판별**                     | `_find_mentions_for_candidate` 후 `_filter_mentions_by_facility`로 **해당 업체에 대한 블로그 언급만** 집계. `_is_mention_of_facility` 등으로 오탐 감소. |
| **근거 거리 `_resolve_distance`** | Kakao 결과는 카카오 좌표, 공공 결과는 사용자와 시설 간 거리.                                                                                          |
| **병합 우선순위**                   | `public`과 `public+kakao`가 동일 업체 후보(`_might_be_same_facility`)면 **공공 레코드 유지** + 카카오 메타(lat/lng/name/address/phone/link) 채움.      |
| **정렬·점수**                     | 내부 가중합(`_W_DISTANCE`, `_W_MENTION`, `_W_FRESHNESS`)으로 **중간 정렬용 `score`**. 이후 `rank_facilities`에서 신호별로 재계산.                      |
| `**source**`                  | 예: `"public"`, `"kakao"`, `"public+kakao"`.                                                                                     |
| **동물병원**                      | 카카오 POI 이름이 사람 병원처럼 보이면 제외 (`_looks_like_human_hospital_name`).                                                                 |


**관측:** `INFO grooming_ranker … mentions=… kakao=… merged_top=… top_score=…`

---

## 6. 최종 랭킹 신호 (`ranker.py`)

`rank_facilities`가 후보별로 신호를 계산하고 `WEIGHT_PRESETS` 또는 **프리셋 없을 때 grooming 프리셋과 동일** 가중치로 가중합한다.


| 신호            | 역할 요약                                                             |
| ------------- | ----------------------------------------------------------------- |
| `distance`    | 거리 근접                                                             |
| `mention`     | 블로그 언급 강도                                                         |
| `trend_match` | Redis 트렌드 키워드 매칭                                                  |
| `history`     | Petory 사용 이력 토큰이 있으면 반영 (`extract_interactions_from_legacy_json`) |
| `pet_match`   | 품종·체형 등과 시설 카테고리 부합                                               |


**컨텍스트별 명시 프리셋 (`WEIGHT_PRESETS`):** `grooming`, `hospital`, `supplies`.  
그 외 `cafe`, `pension`, `restaurant`, `boarding`, `hotel`, `pharmacy` 등은 `**get_weights`에 없으면 grooming과 동일**(기본 프리셋).

출력 각 항목에 `**reasons`**, `**signal_scores**`, `**score`/`mention_score`**가 붙고, `**score` 내림차순 · 동점 시 거리 오름차순** 정렬 후 `top_n` 슬라이스.

---

## 7. 레거시 파이프라인 요약 (`legacy_pipe`)

`GROOMING_MVP_ENABLED=false`일 때 (`recommend.py`의 `legacy_pipe`).

- 공공 `**get_nearby_facilities`**로 후보 조회 후, `source_id`·`facility_id`는 클라이언트용 dict에서 제거하고 `**FacilityItem` 직접 매핑**(멘션·Kakao·중간 병합·신호 랭커 없음).
- 응답: 시설·트렌드 모두 없으면 `recommendation=None`. 그 외 `include_copy`가 참이면 LLM 카피(`generate_recommendation`) 시도, 거짓이면 규칙 카피(`build_context_copy` / 트렌드만이면 `build_trend_only_copy`).

예전 코드베이스의 `search_kakao_places_plain`, `analyze_blog_posts_for_nearby_candidates`, `ollama_legacy_recommend` 등과 **항상 같은 것은 아님**. 현 레포 기준은 위 분기.

---

## 8. 환경 변수·계약 확인

배포 전 최소 확인.


| 변수                                        | 역할                                       |
| ----------------------------------------- | ---------------------------------------- |
| `GROOMING_MVP_ENABLED`                    | MVP 파이프 on/off (**멀티 컨텍스트 공통 게이트**).     |
| `KAKAO_REST_API_KEY`                      | Kakao 검색 필수.                             |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 블로그 검색 + 배치 트렌드. MVP 멘션 경로에도 블로그 API 사용. |


---

## 9. 안전·품질 가드


| 위험                         | 완화                                                    |
| -------------------------- | ----------------------------------------------------- |
| 개인 블로그 인용 과다               | 응답은 **시설 이름 + 공공 레코드** 중심. 원문 블로그 본문은 응답에 넣지 않음.      |
| 잘못된 멘션 집계                  | 이름 정규화·차단 패턴·업체 매칭 휴리스틱. `mention_map`이 비면 트렌드·거리 중심. |
| 외부 API 한도·지연               | Kakao TTL + 세마포어; 블로그 실패 시 폴백.                        |
| Petory 과호출·중복 `request_id` | 클라이언트·게이트웨이에서 디바운스·중복 검토.                             |


---

## 10. 구현 상태

MVP 플래그 및 위 파이프는 코드에 반영됨. 새 컨텍스트를 `ENRICHED_CONTEXTS`에 넣을 때는 `CONTEXT_TO_CATEGORY`·`CONTEXT_TO_FACILITY_TYPE`(`facilities.py`), `kakao.py`의 `_QUERY_SUFFIXES`/`_CONTEXT_HINTS`, `grooming_blog`의 `_CONTEXT_QUERIES`(또는 동등 로직)를 함께 맞춘다.

---

## 11. Petory 적용 미니 체크리스트

- 클라우드 또는 로컬에 `GROOMING_MVP_ENABLED=true` 확인
- `KAKAO_REST_API_KEY` 존재
- `POST /api/pet-data/recommend`가 **enriched 컨텍스트** 문자열 사용
- 브리핑·로그와 `mention_map` 로그 줄 대조

---

## 12. 참고 코드 경로


| 구분          | 파일                                               |
| ----------- | ------------------------------------------------ |
| 라우팅·분기      | `app/serving/api/recommend.py`                   |
| 블로그 멘션      | `app/ingestion/grooming_blog.py`                 |
| Kakao 검색·캐시 | `app/ingestion/kakao.py`                         |
| 공공 반경 후보    | `app/serving/recommender/facilities.py`          |
| 중간 병합·언급 집계 | `app/serving/recommender/grooming_ranker.py`     |
| 최종 신호 랭킹    | `app/serving/recommender/ranker.py`, `signals/`* |


배치 트렌드·수집은 `runner`, `scheduler` 등과 별계. MVP 경로만 보면 `[docs/분석/DATA-AND-API-FLOW.md](분석/DATA-AND-API-FLOW.md)` 참고.

---

## 문서 이력


| 날짜             | 내용                                                                                                          |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| **2026-05-21** | Phase 3 멀티 컨텍스트·통합 브리핑                                                                                      |
| **2026-05-22** | 현행 코드 기준 재정렬: `ENRICHED_CONTEXTS`, `recommend_version`, `ranker` 레이어, Kakao TTL/키·멘션 상한·`context_pipe` 로그 등 |
| **2026-05-22** | 표·패딩 정리(포맷터 과확장 제거), 링크·용어 줄 정돈                                                                             |


