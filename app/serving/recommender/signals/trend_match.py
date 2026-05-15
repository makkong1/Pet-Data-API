"""트렌드 매칭 신호 — 시설명에 최신 트렌드 키워드가 포함되면 점수 부여.

키워드 집합은 SignalContext.trend_keywords (keyword → score) 로 주입.
점수 = (매칭된 키워드들의 trend score 합) / (전체 trend score 합), [0,1] clamp.
"""

from __future__ import annotations

from typing import Optional

from app.serving.recommender.signals.base import SignalContext, clamp01


class TrendMatchSignal:
    name = "trend_match"

    def __init__(self) -> None:
        # candidate idx → 매칭된 키워드 한 개 (reasons 라벨용)
        self._matched_kw: dict[int, str] = {}

    async def score(self, candidates: list[dict], ctx: SignalContext) -> list[float]:
        self._matched_kw.clear()
        if not candidates or not ctx.trend_keywords:
            return [0.0] * len(candidates)

        total = sum(ctx.trend_keywords.values()) or 1
        out: list[float] = []
        for idx, c in enumerate(candidates):
            name_lc = (c.get("name") or "").lower()
            matched_score = 0
            best_kw: Optional[str] = None
            best_w = 0
            for kw, w in ctx.trend_keywords.items():
                if kw and kw.lower() in name_lc:
                    matched_score += w
                    if w > best_w:
                        best_w = w
                        best_kw = kw
            if best_kw:
                self._matched_kw[idx] = best_kw
            out.append(clamp01(matched_score / total))
        return out

    def reason_label(self, candidate: dict, candidate_score: float) -> Optional[str]:
        if candidate_score <= 0:
            return None
        # 후보 객체에 idx 정보가 없으므로, name 기준 다시 찾는 게 안전하지만
        # 호출자가 idx-aware 라면 self._matched_kw 사용. 여기선 단순 라벨만.
        return "trend_match"

    def reason_for_index(self, idx: int) -> Optional[str]:
        kw = self._matched_kw.get(idx)
        return f"trend_match:{kw}" if kw else None
