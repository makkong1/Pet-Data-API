"""블로그 멘션 신호 — candidate['mention_count'] 를 후보 집합 최대값으로 정규화."""

from __future__ import annotations

from typing import Optional

from app.serving.recommender.signals.base import SignalContext, clamp01


class MentionSignal:
    name = "mention"

    async def score(self, candidates: list[dict], ctx: SignalContext) -> list[float]:
        if not candidates:
            return []
        counts = [int(c.get("mention_count") or 0) for c in candidates]
        max_c = max(counts, default=1) or 1
        return [clamp01(c / max_c) for c in counts]

    def reason_label(self, candidate: dict, candidate_score: float) -> Optional[str]:
        if int(candidate.get("mention_count") or 0) >= 1 and candidate_score > 0:
            return "mention"
        return None
