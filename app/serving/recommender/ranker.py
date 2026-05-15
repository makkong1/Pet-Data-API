"""일반화 추천 랭커 — Signal 5종을 가중합으로 결합.

레거시 grooming_ranker 와 동작 호환:
- distance·mention 신호의 정규화 방식은 grooming_ranker 와 동일.
- 멘션·Kakao POI 병합은 호출자(/recommend)가 이미 끝낸 candidates 를 받아 점수만 계산.

호출자는 candidates 에 최소한 다음 필드를 채워야 한다:
    name, distance_m
선택 필드:
    address, lat, lng, source_id, facility_id, mention_count, freshness, source
"""

from __future__ import annotations

import logging
from typing import Optional

from app.serving.recommender.signals.base import Signal, SignalContext, clamp01
from app.serving.recommender.signals.distance import DistanceSignal
from app.serving.recommender.signals.interaction_history import InteractionHistorySignal
from app.serving.recommender.signals.mention import MentionSignal
from app.serving.recommender.signals.pet_match import PetMatchSignal
from app.serving.recommender.signals.trend_match import TrendMatchSignal

_log = logging.getLogger(__name__)


# 컨텍스트별 가중치 프리셋 — 각 합은 1.0.
# - hospital: 가까운 곳이 가장 중요. 펫 매칭(노령 등)도 의미 있음.
# - grooming: 거리 + 블로그 멘션이 핵심. 트렌드는 보조.
# - supplies: 거리 + 트렌드(인기 상품 키워드 매칭).
WEIGHT_PRESETS: dict[str, dict[str, float]] = {
    "grooming": {
        "distance": 0.45,
        "mention":  0.25,
        "trend_match": 0.15,
        "history":  0.10,
        "pet_match": 0.05,
    },
    "hospital": {
        "distance": 0.55,
        "mention":  0.10,
        "trend_match": 0.05,
        "history":  0.20,
        "pet_match": 0.10,
    },
    "supplies": {
        "distance": 0.45,
        "mention":  0.15,
        "trend_match": 0.20,
        "history":  0.15,
        "pet_match": 0.05,
    },
}

_DEFAULT_WEIGHTS = WEIGHT_PRESETS["grooming"]


def get_weights(context: str) -> dict[str, float]:
    return WEIGHT_PRESETS.get(context, _DEFAULT_WEIGHTS)


def default_signals() -> list[Signal]:
    return [
        DistanceSignal(),
        MentionSignal(),
        TrendMatchSignal(),
        InteractionHistorySignal(),
        PetMatchSignal(),
    ]


async def rank_facilities(
    candidates: list[dict],
    ctx: SignalContext,
    top_n: int,
    signals: Optional[list[Signal]] = None,
    weights: Optional[dict[str, float]] = None,
) -> list[dict]:
    """후보들에 신호별 점수를 계산해 가중합으로 정렬 후 상위 top_n 반환.

    각 항목은 원래 dict + {score, reasons, mention_score, signal_scores}.
    """
    if not candidates:
        return []

    signals = signals or default_signals()
    weights = weights or get_weights(ctx.context)

    # 신호별 정규화 점수 행렬: signal_name → [score_per_candidate]
    matrix: dict[str, list[float]] = {}
    for sig in signals:
        try:
            scores = await sig.score(candidates, ctx)
        except Exception as e:
            _log.warning(
                "ranker [%s] signal=%s error=%s — fallback 0.0",
                ctx.request_id, sig.name, type(e).__name__,
            )
            scores = [0.0] * len(candidates)
        if len(scores) != len(candidates):
            scores = (scores + [0.0] * len(candidates))[: len(candidates)]
        matrix[sig.name] = scores

    out: list[dict] = []
    for idx, c in enumerate(candidates):
        signal_scores = {name: matrix[name][idx] for name in matrix}
        total = sum(weights.get(name, 0.0) * signal_scores.get(name, 0.0) for name in signal_scores)
        score = clamp01(total)

        reasons: list[str] = []
        for sig in signals:
            ss = signal_scores.get(sig.name, 0.0)
            if ss <= 0:
                continue
            # TrendMatchSignal 은 매칭 키워드를 라벨에 붙임.
            if isinstance(sig, TrendMatchSignal):
                lab = sig.reason_for_index(idx)
            else:
                lab = sig.reason_label(c, ss)
            if lab and lab not in reasons:
                reasons.append(lab)

        entry = dict(c)
        entry["score"] = round(score, 4)
        entry["reasons"] = reasons
        entry["mention_score"] = round(signal_scores.get("mention", 0.0), 4)
        entry["signal_scores"] = {k: round(v, 4) for k, v in signal_scores.items()}
        out.append(entry)

    out.sort(key=lambda r: (-r["score"], r.get("distance_m") or 0))

    _log.info(
        "ranker [%s] context=%s candidates=%d weights=%s top_n=%d",
        ctx.request_id, ctx.context, len(candidates), weights, top_n,
    )
    return out[:top_n]
