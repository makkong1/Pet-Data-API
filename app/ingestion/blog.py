from datetime import datetime, timezone
from typing import Optional

_FRESHNESS_WINDOW_DAYS = 180
_MIN_MENTION_COUNT = 2
_TOP_N = 20
_EPS = 1e-9


def _parse_freshness(postdate: Optional[str]) -> float:
    if not postdate:
        return 0.0
    try:
        if len(postdate) == 8:
            dt = datetime.strptime(postdate, "%Y%m%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(postdate)
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days < 0 or age_days > _FRESHNESS_WINDOW_DAYS:
            return 0.0
        return round(1.0 - age_days / _FRESHNESS_WINDOW_DAYS, 4)
    except Exception:
        return 0.0


def _compute_scores(aggregator: dict) -> list:
    """aggregator: {name: {"count": int, "freshness_sum": float}}"""
    entries = [
        (name, info)
        for name, info in aggregator.items()
        if info["count"] >= _MIN_MENTION_COUNT
    ]
    if not entries:
        return []

    scored = []
    for name, info in entries:
        count = info["count"]
        avg_freshness = round(info["freshness_sum"] / count, 4)
        raw_score = count * avg_freshness
        scored.append({"name": name, "count": count, "avg_freshness": avg_freshness, "raw_score": raw_score})

    max_raw = max(e["raw_score"] for e in scored)
    if max_raw < _EPS:
        return []

    result = sorted(
        [
            {
                "name": e["name"],
                "mention_count": e["count"],
                "avg_freshness": e["avg_freshness"],
                "score": round(e["raw_score"] / max_raw, 4),
            }
            for e in scored
        ],
        key=lambda x: x["score"],
        reverse=True,
    )[:_TOP_N]
    return result
