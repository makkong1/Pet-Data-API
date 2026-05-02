# Step 6 — 규칙 기반 추천 카피 + 폴백 + 관측성

## 목적
LLM 없이 규칙 기반 추천 문구를 생성하고, 폴백 흐름과 관측성 로그 필드를 완성한다.

## 배경
- SSOT: `docs/GROOMING-RECOMMEND-MVP.md` §4.2, §4.3, §2.6
- LLM(Ollama)은 이 단계에서 사용하지 않는다. 비그루밍 컨텍스트의 레거시 LLM 호출은 유지.
- 폴백: Kakao 실패 → 공공만 (Step 5에서 처리됨), 블로그 실패 → mention=0 (Step 5 처리됨), LLM 없음 → 규칙 문구만.
- 관측성 로그는 PII·원문 스니펫 포함 금지 (카운터·ms만).

## 수정 대상 파일

### 1. `app/serving/recommender/builder.py`

아래 함수 추가 (기존 함수 뒤에):

```python
def build_grooming_copy(facilities: list[dict], trends: list[tuple[str, int]]) -> Optional[str]:
    """그루밍 MVP 규칙 기반 추천 카피 (LLM 없음). §4.2"""
    if facilities:
        n = len(facilities)
        first = facilities[0]
        return (
            f"근처 {n}개 애견 미용 시설을 찾았습니다. "
            f"가장 가까운 {first['name']}까지 {first['distance_m']}m입니다."
        )
    # 시설 없음 → 트렌드 카피
    return build_trend_only_copy("grooming", trends) or None
```

### 2. `app/serving/api/recommend.py`

그루밍 MVP 분기 내 타이밍 계측 및 관측성 로그 추가.  
분기 시작 전 `import time` 확인 (없으면 상단에 추가).

그루밍 분기를 아래처럼 교체:

```python
    if req.context == "grooming" and settings.GROOMING_MVP_ENABLED:
        recommend_version = "grooming-mvp-v1"
        radius_m = req.radius_km * 1000
        t0 = time.monotonic()

        public_raw = await get_nearby_facilities(db, req.lat, req.lng, normalized_context, req.radius_km, req.top_n * 4)

        t_blog = time.monotonic()
        try:
            mention_map, candidate_names = await extract_grooming_mentions()
        except Exception:
            mention_map, candidate_names = {}, []
            _log.warning("grooming_blog_failed")
        blog_ms = int((time.monotonic() - t_blog) * 1000)

        candidate_count_raw = len(mention_map)
        candidate_count_after_cap = len(candidate_names)

        t_kakao = time.monotonic()
        try:
            kakao_map = await search_kakao_places(candidate_names, req.lat, req.lng)
        except Exception:
            kakao_map = {}
            _log.warning("kakao_search_failed")
        kakao_ms = int((time.monotonic() - t_kakao) * 1000)

        kakao_call_count = sum(1 for v in kakao_map.values() if v is not None)

        t_rank = time.monotonic()
        facilities_raw = rank_grooming_facilities(
            public_raw, kakao_map, mention_map, req.lat, req.lng, radius_m, req.top_n
        )
        rank_ms = int((time.monotonic() - t_rank) * 1000)
        total_ms = int((time.monotonic() - t0) * 1000)

        _log.info(
            "grooming_pipe candidate_count_raw=%d after_cap=%d after_match=%d "
            "kakao_calls=%d latency_total=%dms blog=%dms kakao=%dms rank=%dms",
            candidate_count_raw, candidate_count_after_cap, len(facilities_raw),
            kakao_call_count, total_ms, blog_ms, kakao_ms, rank_ms,
        )
    else:
        ...  # 레거시 분기 유지 (Step 5 코드)
```

추천 카피 생성 부분 (그루밍 분기 후, 레거시 분기와 분리):

```python
    if req.context == "grooming" and settings.GROOMING_MVP_ENABLED:
        recommendation = build_grooming_copy(facilities_raw, trends_raw)
    elif not facilities_raw and not trends_raw:
        recommendation = None
    elif not facilities_raw and trends_raw:
        recommendation = build_trend_only_copy(normalized_context, trends_raw) or None
    else:
        pet_dict = req.pet.model_dump() if req.pet else None
        prompt = build_prompt(normalized_context, facilities_raw, [t.model_dump() for t in trends], pet_dict)
        recommendation = await generate_recommendation(prompt)
```

## 완료 기준 (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate

python3 -c "
from app.serving.recommender.builder import build_grooming_copy
r = build_grooming_copy([{'name': '해피독', 'distance_m': 100}], [])
assert '해피독' in r and '100m' in r
r2 = build_grooming_copy([], [('스포팅컷', 10)])
assert r2 is not None
print('Step 6 AC passed')
"
```
