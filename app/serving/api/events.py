"""Petory 콜백 이벤트 수집 — POST /events/recommendation → facility_interactions 적재."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.core.auth import require_api_key
from app.platform.core.database import get_db
from app.platform.schemas.events import (
    RecommendationEventsRequest,
    RecommendationEventsResponse,
)

router = APIRouter(prefix="/events", tags=["이벤트 (Events)"])

_log = logging.getLogger(__name__)


@router.post(
    "/recommendation",
    response_model=RecommendationEventsResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="추천 인터랙션 콜백 (Recommendation interaction callback)",
    description=(
        "POST /recommend 결과에 대한 노출/클릭/예약 이벤트를 받아 facility_interactions 에 적재. "
        "동기 INSERT 지만 202 로 응답해 fire-and-forget 으로 사용하세요."
    ),
)
async def post_recommendation_events(
    payload: RecommendationEventsRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
) -> RecommendationEventsResponse:
    accepted = 0
    skipped = 0

    for ev in payload.events:
        if ev.facility_id is None and not ev.source_id:
            skipped += 1
            continue
        try:
            await db.execute(
                text(
                    """
                    INSERT INTO facility_interactions
                        (request_id, facility_id, source_id, user_ref, event, occurred_at)
                    VALUES
                        (:request_id, :facility_id, :source_id, :user_ref, :event, :occurred_at)
                    """
                ),
                {
                    "request_id": payload.request_id,
                    "facility_id": ev.facility_id,
                    "source_id": ev.source_id,
                    "user_ref": ev.user_ref,
                    "event": ev.event,
                    "occurred_at": ev.occurred_at,
                },
            )
            accepted += 1
        except Exception as e:
            skipped += 1
            _log.warning(
                "events insert failed request_id=%s event=%s err=%s",
                payload.request_id, ev.event, type(e).__name__,
            )

    try:
        await db.commit()
    except Exception as e:
        _log.warning("events commit failed err=%s", type(e).__name__)
        try:
            await db.rollback()
        except Exception:
            pass
        accepted = 0
        skipped = len(payload.events)

    response.status_code = status.HTTP_202_ACCEPTED
    return RecommendationEventsResponse(accepted=accepted, skipped=skipped)
