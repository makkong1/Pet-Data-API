import logging

from app.ingestion.blog import collect_popular_for_context, save_popular
from app.ingestion.naver import CATEGORY_KEYWORDS, collect_category_trends
from app.ingestion.analyzer.trend import aggregate_keywords
from app.platform.cache.redis import save_trend

_log = logging.getLogger(__name__)

_POPULAR_CONTEXTS = [
    "grooming",
    "hospital",
    "supplies",
    "pharmacy",
    "cafe",
    "pension",
    "restaurant",
    "boarding",
    "hotel",
]


async def run_trend_collection() -> list[dict]:
    results = []
    for category in CATEGORY_KEYWORDS:
        try:
            items = await collect_category_trends(category)
            counts = aggregate_keywords(items)
            await save_trend(category, dict(counts))
            results.append({"category": category, "status": "success", "keywords_count": len(counts)})
        except Exception as e:
            _log.error("trend collection failed category=%s err=%s", category, e)
            results.append({"category": category, "status": "failed", "error_message": str(e)})
    return results


async def run_popular_collection() -> list[dict]:
    results = []
    for context in _POPULAR_CONTEXTS:
        try:
            popular = await collect_popular_for_context(context)
            await save_popular(context, popular)
            results.append({"context": context, "status": "success", "count": len(popular)})
        except Exception as e:
            _log.error("popular collection failed context=%s err=%s", context, e)
            results.append({"context": context, "status": "failed", "error_message": str(e)})
    return results
