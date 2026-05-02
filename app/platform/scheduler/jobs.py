from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.platform.core.database import AsyncSessionLocal
from app.ingestion.runner import run_collection, run_trend_collection

scheduler = AsyncIOScheduler()


async def scheduled_collection():
    async with AsyncSessionLocal() as db:
        await run_collection(db)


async def scheduled_trend_collection():
    await run_trend_collection()


def start_scheduler():
    scheduler.add_job(
        scheduled_trend_collection,
        trigger="cron",
        hour=18,
        minute=0,
        max_instances=1,
        id="daily_trend_collection",
    )
    scheduler.add_job(
        scheduled_collection,
        trigger="cron",
        hour=18,
        minute=5,
        max_instances=1,
        id="daily_collection",
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
