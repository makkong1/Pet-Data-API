"""Petory 가 보내는 인터랙션 이벤트 콜백 스키마."""

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, field_validator


EventType = Literal["view", "click", "book"]


class InteractionEvent(BaseModel):
    facility_id: Optional[int] = Field(
        None,
        description="pet_facilities.id (Kakao-only 후보일 땐 비우고 source_id 채움)",
    )
    source_id: Optional[str] = Field(
        None,
        max_length=100,
        description="공공·외부 식별자 (facility_id 미상 시)",
    )
    user_ref: Optional[str] = Field(
        None,
        max_length=64,
        description="Petory 익명화 사용자 식별자 (있으면 클릭/사용자 매핑)",
    )
    event: EventType = Field(..., description="이벤트 타입: view | click | book")
    occurred_at: datetime = Field(..., description="이벤트 발생 시각 (ISO 8601)")

    @field_validator("source_id")
    @classmethod
    def _at_least_one_identifier(cls, v, info):
        return v


class RecommendationEventsRequest(BaseModel):
    request_id: Optional[str] = Field(
        None,
        max_length=32,
        description="POST /recommend 응답의 request_id (있으면 노출→클릭 매핑)",
    )
    events: List[InteractionEvent] = Field(
        ..., min_length=1, max_length=100, description="이벤트 묶음"
    )


class RecommendationEventsResponse(BaseModel):
    accepted: int = Field(..., description="실제로 적재된 이벤트 수")
    skipped: int = Field(0, description="식별자가 부족해 무시된 이벤트 수")
