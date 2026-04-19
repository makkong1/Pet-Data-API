from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.collector.business import fetch_businesses, extract_businesses
from app.collector.hospital import fetch_hospitals, extract_hospitals
from app.models.log import CollectionLog


async def _upsert_facility(db: AsyncSession, item: dict) -> bool:
    if not item.get("source_id") or not item.get("name"):
        return False

    facility_type = item["type"]

    await db.execute(
        text("""
            INSERT INTO pet_facilities
                (source_id, type, name, status, address,
                 region_city, region_district, phone, collected_at)
            VALUES
                (:source_id, :type, :name, :status, :address,
                 :region_city, :region_district, :phone, NOW())
            ON CONFLICT (source_id) DO UPDATE SET
                name            = EXCLUDED.name,
                status          = EXCLUDED.status,
                address         = EXCLUDED.address,
                region_city     = EXCLUDED.region_city,
                region_district = EXCLUDED.region_district,
                phone           = EXCLUDED.phone,
                collected_at    = NOW()
        """),
        item,
    )

    result = await db.execute(
        text("SELECT id FROM pet_facilities WHERE source_id = :source_id"),
        {"source_id": item["source_id"]},
    )
    facility_id = result.scalar_one()

    if facility_type == "BUSINESS":
        await db.execute(
            text("""
                INSERT INTO business_details (facility_id, business_type, registration_no)
                VALUES (:facility_id, :business_type, :registration_no)
                ON CONFLICT (facility_id) DO UPDATE SET
                    business_type   = EXCLUDED.business_type,
                    registration_no = EXCLUDED.registration_no
            """),
            {
                "facility_id": facility_id,
                "business_type": item.get("business_type", ""),
                "registration_no": item.get("registration_no"),
            },
        )
    elif facility_type == "HOSPITAL":
        await db.execute(
            text("""
                INSERT INTO hospital_details (facility_id, license_no, specialty)
                VALUES (:facility_id, :license_no, :specialty)
                ON CONFLICT (facility_id) DO UPDATE SET
                    license_no = EXCLUDED.license_no,
                    specialty  = EXCLUDED.specialty
            """),
            {
                "facility_id": facility_id,
                "license_no": item.get("license_no"),
                "specialty": item.get("specialty"),
            },
        )
    return True


async def _collect_source(
    db: AsyncSession,
    source_name: str,
    fetch_fn,
    extract_fn,
) -> dict:
    log = CollectionLog(
        source=source_name,
        status="failed",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    await db.flush()

    try:
        response = await fetch_fn()
        items = extract_fn(response)
        log.total_fetched = len(items)

        saved = 0
        for item in items:
            if await _upsert_facility(db, item):
                saved += 1

        log.total_saved = saved
        log.status = "success" if saved == len(items) else "partial"
        log.finished_at = datetime.utcnow()
        await db.commit()
    except Exception as e:
        await db.rollback()
        log.error_message = str(e)
        log.status = "failed"
        log.finished_at = datetime.utcnow()
        db.add(log)
        await db.commit()

    return {
        "source": log.source,
        "status": log.status,
        "total_fetched": log.total_fetched,
        "total_saved": log.total_saved,
        "error_message": log.error_message,
        "started_at": log.started_at,
        "finished_at": log.finished_at,
    }


async def run_collection(db: AsyncSession) -> list:
    logs = []
    logs.append(await _collect_source(db, "petShop", fetch_businesses, extract_businesses))
    logs.append(await _collect_source(db, "animalHospital", fetch_hospitals, extract_hospitals))
    return logs
