from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.ingestion.runner import run_trend_collection

scheduler = AsyncIOScheduler()


def start_scheduler():
    scheduler.add_job(
        run_trend_collection,
        trigger="cron",
        hour=18,
        minute=0,
        max_instances=1,
        id="daily_trend_collection",
    )
    scheduler.start()


def stop_scheduler():
    scheduler.shutdown(wait=False)
