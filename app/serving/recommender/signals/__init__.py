"""랭킹 신호 모듈 — 각 신호는 candidates → [0, 1] 점수 리스트를 반환."""

from app.serving.recommender.signals.distance import DistanceSignal
from app.serving.recommender.signals.interaction_history import InteractionHistorySignal
from app.serving.recommender.signals.mention import MentionSignal
from app.serving.recommender.signals.pet_match import PetMatchSignal
from app.serving.recommender.signals.trend_match import TrendMatchSignal

__all__ = [
    "DistanceSignal",
    "InteractionHistorySignal",
    "MentionSignal",
    "PetMatchSignal",
    "TrendMatchSignal",
]
