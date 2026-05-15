"""트렌드 시계열 적재·조회 — Redis(핫 캐시)와 별개로 Postgres `trend_snapshots`에 일별 누적."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.core.database import AsyncSessionLocal


async def persist_trend_snapshot(
    category: str,
    keyword_counts: dict[str, int],
    snapshot_date: date | None = None,
) -> int:
    """카테고리별 키워드 점수를 `trend_snapshots` 에 upsert.

    같은 (snapshot_date, category, keyword) 가 다시 들어오면 score 를 덮어쓴다.
    같은 날 같은 카테고리에서 이전 수집에 있었지만 이번엔 사라진 키워드는 보존(절삭 없음).
    반환값은 적재한 행 수.
    """
    if not keyword_counts:
        return 0
    snap = snapshot_date or date.today()

    rows = [
        {
            "snapshot_date": snap,
            "category": category,
            "keyword": k,
            "score": int(v),
        }
        for k, v in keyword_counts.items()
    ]

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                INSERT INTO trend_snapshots (snapshot_date, category, keyword, score)
                VALUES (:snapshot_date, :category, :keyword, :score)
                ON CONFLICT (snapshot_date, category, keyword) DO UPDATE
                SET score = EXCLUDED.score,
                    collected_at = NOW()
                """
            ),
            rows,
        )
        await db.commit()
    return len(rows)


async def fetch_trend_timeseries(
    db: AsyncSession,
    category: str,
    days: int,
    top_keywords: int = 10,
) -> list[dict]:
    """카테고리 시계열 — 최근 `days` 일치 일자 × 상위 키워드 그리드.

    상위 키워드는 가장 최근 스냅샷 기준 score 내림차순 top `top_keywords`.
    반환: [{date: 'YYYY-MM-DD', keyword: str, score: int}, ...] (date 오름차순).
    """
    today = date.today()
    since = today - timedelta(days=days - 1)

    result = await db.execute(
        text(
            """
            WITH latest AS (
                SELECT MAX(snapshot_date) AS d
                FROM trend_snapshots
                WHERE category = :category
            ),
            top_kw AS (
                SELECT keyword
                FROM trend_snapshots, latest
                WHERE category = :category
                  AND snapshot_date = latest.d
                ORDER BY score DESC
                LIMIT :top_keywords
            )
            SELECT snapshot_date, keyword, score
            FROM trend_snapshots
            WHERE category = :category
              AND snapshot_date >= :since
              AND keyword IN (SELECT keyword FROM top_kw)
            ORDER BY snapshot_date ASC, score DESC
            """
        ),
        {"category": category, "since": since, "top_keywords": top_keywords},
    )
    rows = result.mappings().all()
    return [
        {
            "date": r["snapshot_date"].isoformat(),
            "keyword": r["keyword"],
            "score": int(r["score"]),
        }
        for r in rows
    ]
