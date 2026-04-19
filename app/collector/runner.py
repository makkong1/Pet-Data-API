from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.collector.client import fetch_abandoned_animals
from app.collector.parser import extract_items
from app.core.config import settings
from app.models.log import CollectionLog


async def run_collection(db: AsyncSession) -> CollectionLog:
    log = CollectionLog(
        source="abandonmentPublic",
        status="failed",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    await db.flush()

    try:
        response = await fetch_abandoned_animals(settings.PUBLIC_DATA_API_KEY)
        items = extract_items(response)
        log.total_fetched = len(items)

        saved = 0
        for item in items:
            if not item.get("notice_no"):
                continue
            await db.execute(
                text("""
                    INSERT INTO abandoned_animals
                        (notice_no, animal_type, breed, age, gender, region,
                         shelter_name, status, notice_date, collected_at)
                    VALUES
                        (:notice_no, :animal_type, :breed, :age, :gender, :region,
                         :shelter_name, :status, :notice_date, NOW())
                    ON CONFLICT (notice_no) DO UPDATE SET
                        animal_type  = EXCLUDED.animal_type,
                        breed        = EXCLUDED.breed,
                        age          = EXCLUDED.age,
                        gender       = EXCLUDED.gender,
                        region       = EXCLUDED.region,
                        shelter_name = EXCLUDED.shelter_name,
                        status       = EXCLUDED.status,
                        notice_date  = EXCLUDED.notice_date,
                        collected_at = NOW()
                """),
                item,
            )
            saved += 1

        log.total_saved = saved
        log.status = "success" if saved == len(items) else "partial"
        await db.commit()

        # 통계 MV 갱신
        await db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_region_stats"))
        await db.commit()

    except Exception as e:
        await db.rollback()
        log.error_message = str(e)
        log.status = "failed"
        await db.commit()

    log.finished_at = datetime.utcnow()
    await db.commit()
    return log
