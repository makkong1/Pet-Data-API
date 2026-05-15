"""인터랙션 이력 신호 — `facility_interactions` 14일치 click 카운트 기반.

후보의 facility_id 가 있으면 SUM(클릭), 없으면 source_id 기준. DB 가 없거나 실패하면 0.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from app.serving.recommender.signals.base import SignalContext, clamp01


class InteractionHistorySignal:
    name = "history"

    def __init__(self, window_days: int = 14, event: str = "click") -> None:
        self.window_days = window_days
        self.event = event

    async def score(self, candidates: list[dict], ctx: SignalContext) -> list[float]:
        if not candidates or ctx.db is None:
            return [0.0] * len(candidates)

        facility_ids = [
            int(c["facility_id"])
            for c in candidates
            if c.get("facility_id") is not None
        ]
        source_ids = [
            str(c["source_id"])
            for c in candidates
            if not c.get("facility_id") and c.get("source_id")
        ]

        counts_by_fid: dict[int, int] = {}
        counts_by_sid: dict[str, int] = {}

        try:
            if facility_ids:
                result = await ctx.db.execute(
                    text(
                        "SELECT facility_id, COUNT(*) AS c "
                        "FROM facility_interactions "
                        "WHERE event = :event "
                        "AND occurred_at >= NOW() - (:days || ' days')::interval "
                        "AND facility_id = ANY(:fids) "
                        "GROUP BY facility_id"
                    ),
                    {"event": self.event, "days": self.window_days, "fids": facility_ids},
                )
                for row in result.mappings().all():
                    counts_by_fid[int(row["facility_id"])] = int(row["c"])

            if source_ids:
                result = await ctx.db.execute(
                    text(
                        "SELECT source_id, COUNT(*) AS c "
                        "FROM facility_interactions "
                        "WHERE event = :event "
                        "AND occurred_at >= NOW() - (:days || ' days')::interval "
                        "AND facility_id IS NULL "
                        "AND source_id = ANY(:sids) "
                        "GROUP BY source_id"
                    ),
                    {"event": self.event, "days": self.window_days, "sids": source_ids},
                )
                for row in result.mappings().all():
                    counts_by_sid[str(row["source_id"])] = int(row["c"])
        except Exception:
            return [0.0] * len(candidates)

        raw: list[int] = []
        for c in candidates:
            fid = c.get("facility_id")
            sid = c.get("source_id")
            if fid is not None and int(fid) in counts_by_fid:
                raw.append(counts_by_fid[int(fid)])
            elif sid and sid in counts_by_sid:
                raw.append(counts_by_sid[str(sid)])
            else:
                raw.append(0)

        max_c = max(raw, default=1) or 1
        return [clamp01(v / max_c) for v in raw]

    def reason_label(self, candidate: dict, candidate_score: float) -> Optional[str]:
        return "history" if candidate_score >= 0.2 else None
