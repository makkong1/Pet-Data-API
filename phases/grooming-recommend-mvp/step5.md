# Step 5 — API 스키마 확장 및 핸들러 분기

## 목적
`FacilityItem`에 그루밍 MVP 필드를 추가하고, `/recommend` 핸들러에 `context=grooming + GROOMING_MVP_ENABLED=true` 분기를 연결한다.

## 배경
- SSOT: `docs/GROOMING-RECOMMEND-MVP.md` §3, §1.1
- 신규 필드는 기본값을 가지므로 기존 레거시 응답(비그루밍, 플래그 off)은 변경 없음.
- `recommend_version`은 항상 문자열로 내려간다 (null 생략 금지, §3).

## 수정 대상 파일

### 1. `app/platform/schemas/recommend.py`

**`FacilityItem`** 에 아래 필드 추가 (기존 필드 뒤에):
```python
    mention_count: int = Field(0, description="블로그 멘션 수 (0=없음·실패)")
    mention_score: float = Field(0.0, description="멘션 정규화 점수 [0.0-1.0]")
    source: str = Field("public", description="데이터 출처: public | kakao | public+kakao")
    score: float = Field(0.0, description="최종 랭킹 점수 [0.0-1.0]")
```

**`RecommendResponse`** 에 아래 필드 추가 (`context` 필드 바로 다음):
```python
    recommend_version: str = Field("legacy", description="응답 파이프 버전")
```

### 2. `app/serving/api/recommend.py`

상단 import에 추가:
```python
from app.platform.core.config import settings
from app.ingestion.grooming_blog import extract_grooming_mentions
from app.ingestion.kakao import search_kakao_places
from app.serving.recommender.grooming_ranker import rank_grooming_facilities
from app.serving.recommender.builder import build_grooming_copy
```

`recommend()` 함수 내 `facilities_raw` 생성 부분을 아래로 교체:

```python
    recommend_version = "legacy"

    if req.context == "grooming" and settings.GROOMING_MVP_ENABLED:
        # ── 그루밍 MVP 파이프 (§1.1)
        recommend_version = "grooming-mvp-v1"
        radius_m = req.radius_km * 1000

        # 공공 DB 반경 목록 (source_id 포함)
        public_raw = await get_nearby_facilities(db, req.lat, req.lng, normalized_context, req.radius_km, req.top_n * 4)

        # 블로그 멘션 추출 (실패 시 폴백: 멘션 없음)
        try:
            mention_map, candidate_names = await extract_grooming_mentions()
        except Exception:
            mention_map, candidate_names = {}, []
            _log.warning("grooming_blog_failed: mention fallback to 0")

        # Kakao 장소 검색 (실패 시 폴백: 공공만)
        try:
            kakao_map = await search_kakao_places(candidate_names, req.lat, req.lng)
        except Exception:
            kakao_map = {}
            _log.warning("kakao_search_failed: kakao fallback to empty")

        facilities_raw = rank_grooming_facilities(
            public_raw, kakao_map, mention_map, req.lat, req.lng, radius_m, req.top_n
        )
    else:
        # ── 레거시 파이프 (비그루밍 또는 플래그 off)
        public_raw = await get_nearby_facilities(db, req.lat, req.lng, normalized_context, req.radius_km, req.top_n)
        # 레거시는 source_id를 FacilityItem에 넘기지 않으므로 pop
        facilities_raw = [{k: v for k, v in f.items() if k != "source_id"} for f in public_raw]
```

`FacilityItem` 생성 부분:
```python
    facilities = [FacilityItem(**{k: v for k, v in f.items() if k != "source_id"}) for f in facilities_raw]
```

`RecommendResponse` 생성 시 `recommend_version` 추가:
```python
    response = RecommendResponse(
        context=req.context,
        recommend_version=recommend_version,
        facilities=facilities,
        trends=trends,
        recommendation=recommendation,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
```

## 완료 기준 (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate

# 스키마 import 오류 없음
python3 -c "from app.platform.schemas.recommend import FacilityItem, RecommendResponse; f=FacilityItem(name='테스트', distance_m=100, address='서울'); assert f.mention_count==0; assert f.score==0.0; assert f.source=='public'; r=RecommendResponse(context='grooming', recommend_version='legacy', facilities=[], trends=[], generated_at='2024-01-01T00:00:00Z'); assert r.recommend_version=='legacy'; print('Step 5 schema AC passed')"

# 앱 기동 오류 없음
python3 -c "from app.main import app; print('Step 5 app import passed')"
```
