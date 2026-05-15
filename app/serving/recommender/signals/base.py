"""신호 인터페이스 — context · candidates 받고 정규화 점수 리스트 반환."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SignalContext:
    """랭킹 호출 1회분의 공통 입력. 모든 신호가 공유한다."""

    user_lat: float
    user_lng: float
    radius_m: float
    context: str  # grooming / hospital / supplies
    pet: dict | None = None
    db: AsyncSession | None = None
    # 트렌드 키워드 (keyword → score). TrendMatchSignal 이 사용.
    trend_keywords: dict[str, int] = field(default_factory=dict)
    request_id: str = "-"


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


class Signal(Protocol):
    """신호 프로토콜.

    name      : reasons 라벨용 식별자 (예: 'distance', 'trend_match').
    score(...) : len(candidates) 와 같은 길이의 [0.0, 1.0] 리스트 반환.
    """

    name: str

    async def score(self, candidates: list[dict], ctx: SignalContext) -> list[float]: ...

    def reason_label(self, candidate: dict, candidate_score: float) -> Optional[str]:
        """후보별 reasons 에 들어갈 라벨. 기여가 미미하면 None 반환."""
        ...
