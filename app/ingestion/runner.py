import logging
from datetime import datetime, timezone

from app.ingestion.blog import collect_popular_for_context, save_popular
from app.ingestion.location import enrich_with_location
from app.ingestion.naver import CATEGORY_KEYWORDS, collect_category_trends
from app.ingestion.analyzer.trend import aggregate_keywords
from app.platform.cache.redis import save_trend
from app.platform.store.sqlite import init_db, save_posts
from app.platform import ingestion_digest as idlog

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
    await init_db()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    collected_at = datetime.now(timezone.utc).isoformat()

    results = []
    ok = failed = skipped = 0
    for category in CATEGORY_KEYWORDS:
        try:
            items = await collect_category_trends(category)
            await save_posts(
                items,
                run_id=run_id,
                pipeline="trends",
                category=category,
                query=category,
                collected_at=collected_at,
            )
            counts = aggregate_keywords(items)
            if not counts:
                idlog.log_trend_skipped(
                    category,
                    blog_items=len(items),
                    reason="empty_counter_after_aggregate",
                )
                results.append(
                    {"category": category, "status": "skipped_empty", "keywords_count": 0}
                )
                skipped += 1
                continue
            await save_trend(category, dict(counts))
            idlog.log_trend_stored(
                category,
                blog_items=len(items),
                term_count=len(counts),
                counts=counts,
            )
            results.append({"category": category, "status": "success", "keywords_count": len(counts)})
            ok += 1
        except Exception as e:
            failed += 1
            _log.error("trend collection failed category=%s err=%s", category, e)
            results.append({"category": category, "status": "failed", "error_message": str(e)})

    idlog.log_batch_summary(
        "run_trend_collection", ok=ok, failed=failed, skipped=skipped, detail=results
    )
    return results


async def run_popular_collection() -> list[dict]:
    results = []
    ok = failed = skipped = 0
    for context in _POPULAR_CONTEXTS:
        try:
            popular = await collect_popular_for_context(context)
            if not popular:
                idlog.log_popular_empty(context)
                results.append({"context": context, "status": "skipped_empty", "count": 0})
                skipped += 1
                continue
            popular = await enrich_with_location(popular, context)
            await save_popular(context, popular)
            idlog.log_popular_stored(context, entries=popular)
            results.append({"context": context, "status": "success", "count": len(popular)})
            ok += 1
        except Exception as e:
            failed += 1
            _log.error("popular collection failed context=%s err=%s", context, e)
            results.append({"context": context, "status": "failed", "error_message": str(e)})

    idlog.log_batch_summary(
        "run_popular_collection", ok=ok, failed=failed, skipped=skipped, detail=results
    )
    return results
