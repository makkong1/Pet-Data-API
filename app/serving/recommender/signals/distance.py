"""거리 신호 — 가까울수록 1.0, 반경 끝에 가까울수록 0.0."""

from __future__ import annotations

from typing import Optional

from app.serving.recommender.signals.base import SignalContext, clamp01


class DistanceSignal:
    name = "distance"

    async def score(self, candidates: list[dict], ctx: SignalContext) -> list[float]:
        if not candidates:
            return []
        # 후보 중 가장 멀거나 반경 중 더 큰 값을 정규화 분모로 사용.
        max_d = max((float(c.get("distance_m") or 0) for c in candidates), default=1.0)
        denom = max(max_d, ctx.radius_m, 1.0)
        return [clamp01(1.0 - float(c.get("distance_m") or 0) / denom) for c in candidates]

    def reason_label(self, candidate: dict, candidate_score: float) -> Optional[str]:
        return "distance" if candidate_score >= 0.5 else None
