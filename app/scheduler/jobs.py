from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import AsyncSessionLocal
from app.collector.runner import run_collection

scheduler = AsyncIOScheduler()


async def scheduled_collection():
    async with AsyncSessionLocal() as db:
        await run_collection(db)


def start_scheduler():
    scheduler.add_job(
        scheduled_collection,
        trigger="cron",
        hour=2,
        minute=0,
        max_instances=1,
        id="daily_collection",
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
