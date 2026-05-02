"""배치 수집 진입점: 공공 시설 적재·네이버 트렌드→Redis. API 요청 경로와 분리 — 상세 docs/INGESTION-VS-SERVING.md."""

from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.ingestion.business import fetch_all_businesses
from app.ingestion.hospital import fetch_all_hospitals
from app.ingestion.geocoder import geocode_address
from app.ingestion.naver import collect_category_trends, CATEGORY_KEYWORDS
from app.ingestion.analyzer.trend import aggregate_keywords
from app.platform.cache.redis import save_trend
from app.platform.models.log import CollectionLog


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
    # 좌표 없는 시설 → geocode 시도 (실패해도 무시)
    coord_check = await db.execute(
        text("SELECT lat FROM pet_facilities WHERE source_id = :source_id"),
        {"source_id": item["source_id"]},
    )
    if coord_check.scalar_one_or_none() is None:
        coords = await geocode_address(item.get("address", ""))
        if coords:
            lat, lng = coords
            await db.execute(
                text("UPDATE pet_facilities SET lat = :lat, lng = :lng WHERE source_id = :source_id"),
                {"lat": lat, "lng": lng, "source_id": item["source_id"]},
            )
    return True


async def _collect_source(
    db: AsyncSession,
    source_name: str,
    collect_fn,
) -> dict:
    log = CollectionLog(
        source=source_name,
        status="failed",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    await db.flush()

    try:
        items = await collect_fn()
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
    logs.append(await _collect_source(db, "petShop", fetch_all_businesses))
    logs.append(await _collect_source(db, "animalHospital", fetch_all_hospitals))
    return logs


async def run_trend_collection() -> list[dict]:
    results = []
    for category in CATEGORY_KEYWORDS:
        try:
            items = await collect_category_trends(category)
            counts = aggregate_keywords(items)
            await save_trend(category, dict(counts))
            results.append({
                "category": category,
                "status": "success",
                "keywords_count": len(counts),
            })
        except Exception as e:
            results.append({
                "category": category,
                "status": "failed",
                "error_message": str(e),
            })
    return results


async def run_collection_by_scope(db: AsyncSession, scope: str = "facilities") -> dict:
    if scope == "facilities":
        return {"scope": scope, "facility_logs": await run_collection(db)}
    if scope == "trends":
        return {"scope": scope, "trend_logs": await run_trend_collection()}
    if scope == "all":
        return {
            "scope": scope,
            "trend_logs": await run_trend_collection(),
            "facility_logs": await run_collection(db),
        }
    raise ValueError(f"Unknown collect scope: {scope}")
