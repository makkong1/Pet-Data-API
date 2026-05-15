"""추천 호출 적재 — recommendation_log INSERT. 실패해도 응답에 영향 없도록 캐치."""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)


async def persist_recommendation_log(
    db: AsyncSession,
    request_id: str,
    context: str,
    lat: float,
    lng: float,
    radius_km: float,
    top_n: int,
    pet_payload: Optional[dict],
    facility_ids: list[Optional[int]],
    facility_scores: list[float],
    recommend_version: str,
) -> None:
    """recommendation_log 에 1행 INSERT. UNIQUE(request_id) 충돌 시 무시."""
    try:
        await db.execute(
            text(
                """
                INSERT INTO recommendation_log
                    (request_id, context, lat, lng, radius_km, top_n,
                     pet_payload, facility_ids, facility_scores, recommend_version)
                VALUES
                    (:request_id, :context, :lat, :lng, :radius_km, :top_n,
                     CAST(:pet_payload AS JSONB), :facility_ids, :facility_scores, :recommend_version)
                ON CONFLICT (request_id) DO NOTHING
                """
            ),
            {
                "request_id": request_id,
                "context": context,
                "lat": lat,
                "lng": lng,
                "radius_km": radius_km,
                "top_n": top_n,
                "pet_payload": json.dumps(pet_payload) if pet_payload else None,
                # facility_ids 안에 None 이 섞이면 INT[] 캐스팅 실패할 수 있어 None 제외.
                "facility_ids": [fid for fid in facility_ids if fid is not None],
                "facility_scores": [float(s) for s in facility_scores],
                "recommend_version": recommend_version,
            },
        )
        await db.commit()
    except Exception as e:
        _log.warning(
            "recommendation_log insert failed [%s] context=%s err=%s",
            request_id, context, type(e).__name__,
        )
        try:
            await db.rollback()
        except Exception:
            pass
