"""Phase 2: 일반화 ranker 단위 테스트 — 신호 동작·가중치·reasons."""

import pytest

from app.serving.recommender.ranker import (
    WEIGHT_PRESETS,
    get_weights,
    rank_facilities,
)
from app.serving.recommender.signals.base import SignalContext
from app.serving.recommender.signals.distance import DistanceSignal
from app.serving.recommender.signals.mention import MentionSignal
from app.serving.recommender.signals.pet_match import PetMatchSignal, _is_senior
from app.serving.recommender.signals.trend_match import TrendMatchSignal


@pytest.mark.asyncio
async def test_distance_signal_closer_is_higher():
    sig = DistanceSignal()
    ctx = SignalContext(user_lat=0, user_lng=0, radius_m=1000, context="grooming")
    scores = await sig.score(
        [{"distance_m": 100}, {"distance_m": 500}, {"distance_m": 900}], ctx
    )
    assert scores[0] > scores[1] > scores[2]
    assert all(0.0 <= s <= 1.0 for s in scores)


@pytest.mark.asyncio
async def test_mention_signal_max_normalized():
    sig = MentionSignal()
    ctx = SignalContext(user_lat=0, user_lng=0, radius_m=1000, context="grooming")
    scores = await sig.score(
        [{"mention_count": 0}, {"mention_count": 3}, {"mention_count": 10}], ctx
    )
    assert scores == [0.0, 0.3, 1.0]


@pytest.mark.asyncio
async def test_trend_match_signal_matches_keyword_in_name():
    sig = TrendMatchSignal()
    ctx = SignalContext(
        user_lat=0, user_lng=0, radius_m=1000, context="supplies",
        trend_keywords={"오리젠": 10, "로얄캐닌": 5},
    )
    candidates = [
        {"name": "오리젠 펫샵"},  # contains '오리젠'
        {"name": "동네 가게"},
    ]
    scores = await sig.score(candidates, ctx)
    assert scores[0] > scores[1]
    assert sig.reason_for_index(0) == "trend_match:오리젠"
    assert sig.reason_for_index(1) is None


@pytest.mark.asyncio
async def test_pet_match_species_token():
    sig = PetMatchSignal()
    ctx = SignalContext(
        user_lat=0, user_lng=0, radius_m=1000, context="grooming",
        pet={"type": "cat", "breed": None, "age": "2살"},
    )
    scores = await sig.score(
        [
            {"name": "고양이 전문 미용실", "facility_id": None},
            {"name": "강아지 미용실", "facility_id": None},
        ],
        ctx,
    )
    assert scores[0] > scores[1]


def test_is_senior_threshold():
    assert _is_senior("12살") is True
    assert _is_senior("3세") is False
    assert _is_senior("senior care") is True
    assert _is_senior("") is False


def test_weight_presets_sum_to_one():
    for context, weights in WEIGHT_PRESETS.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-9, f"{context} weights sum {total} != 1.0"


def test_get_weights_unknown_context_falls_back():
    assert get_weights("nonexistent") == WEIGHT_PRESETS["grooming"]


@pytest.mark.asyncio
async def test_rank_facilities_combines_signals_into_score():
    candidates = [
        {
            "name": "해피독 미용실",
            "address": "서울",
            "distance_m": 100,
            "mention_count": 5,
            "lat": 37.5, "lng": 127.0,
            "facility_id": 1,
            "source_id": "B001",
        },
        {
            "name": "먼 가게",
            "address": "서울",
            "distance_m": 2500,
            "mention_count": 0,
            "lat": 37.6, "lng": 127.0,
            "facility_id": 2,
            "source_id": "B002",
        },
    ]
    ctx = SignalContext(
        user_lat=37.5, user_lng=127.0, radius_m=3000, context="grooming",
        pet={"type": "dog", "breed": "말티즈", "age": "2살"},
        trend_keywords={"미용실": 8},
    )
    result = await rank_facilities(candidates, ctx, top_n=2)
    assert len(result) == 2
    # 가까우면서 멘션 있고 트렌드 매칭되는 첫 후보가 위로.
    assert result[0]["name"] == "해피독 미용실"
    assert result[0]["score"] > result[1]["score"]
    # reasons 에 distance 또는 trend_match 가 들어가야 함.
    assert "distance" in result[0]["reasons"]
    assert any(r.startswith("trend_match") for r in result[0]["reasons"])
    # mention_score 가 채워짐.
    assert result[0]["mention_score"] > result[1]["mention_score"]


@pytest.mark.asyncio
async def test_rank_facilities_pet_changes_order(monkeypatch):
    """같은 후보·좌표에서 펫 종을 바꾸면 pet_match 가 순위에 영향을 줘야 함."""
    candidates = [
        {"name": "고양이 전문 미용", "distance_m": 500, "mention_count": 1, "facility_id": None, "source_id": "C1"},
        {"name": "강아지 전문 미용", "distance_m": 500, "mention_count": 1, "facility_id": None, "source_id": "D1"},
    ]
    ctx_cat = SignalContext(
        user_lat=0, user_lng=0, radius_m=1000, context="grooming",
        pet={"type": "cat", "breed": None, "age": "2살"},
    )
    ctx_dog = SignalContext(
        user_lat=0, user_lng=0, radius_m=1000, context="grooming",
        pet={"type": "dog", "breed": None, "age": "2살"},
    )
    cat = await rank_facilities(candidates, ctx_cat, top_n=2)
    dog = await rank_facilities(candidates, ctx_dog, top_n=2)

    assert cat[0]["name"] == "고양이 전문 미용"
    assert dog[0]["name"] == "강아지 전문 미용"


@pytest.mark.asyncio
async def test_rank_facilities_empty_returns_empty():
    ctx = SignalContext(user_lat=0, user_lng=0, radius_m=1000, context="grooming")
    assert await rank_facilities([], ctx, top_n=5) == []
