from app.ingestion.naver import collect_category_trends, CATEGORY_KEYWORDS
from app.ingestion.analyzer.trend import aggregate_keywords
from app.platform.cache.redis import save_trend


async def run_trend_collection() -> list[dict]:
    results = []
    for category in CATEGORY_KEYWORDS:
        try:
            items = await collect_category_trends(category)
            counts = aggregate_keywords(items)
            await save_trend(category, dict(counts))
            results.append({"category": category, "status": "success", "keywords_count": len(counts)})
        except Exception as e:
            results.append({"category": category, "status": "failed", "error_message": str(e)})
    return results
