"""lat/lng가 NULL인 pet_facilities 레코드를 Kakao 지오코딩으로 일괄 채운다."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.platform.core.config import settings
from app.ingestion.geocoder import geocode_address


async def run():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        result = await db.execute(
            text("SELECT id, name, address FROM pet_facilities WHERE lat IS NULL ORDER BY id")
        )
        rows = result.fetchall()

    print(f"geocoding 대상: {len(rows)}건")
    ok = fail = 0

    for row in rows:
        fid, name, address = row
        coords = await geocode_address(address or "")
        async with Session() as db:
            if coords:
                lat, lng = coords
                await db.execute(
                    text("UPDATE pet_facilities SET lat = :lat, lng = :lng WHERE id = :id"),
                    {"lat": lat, "lng": lng, "id": fid},
                )
                await db.commit()
                print(f"  ✓ [{fid}] {name} → ({lat:.5f}, {lng:.5f})")
                ok += 1
            else:
                print(f"  ✗ [{fid}] {name} | {address}")
                fail += 1
        await asyncio.sleep(0.05)  # Kakao QPS 제한 대응

    print(f"\n완료 — 성공: {ok}, 실패: {fail} / 전체: {len(rows)}")


if __name__ == "__main__":
    asyncio.run(run())
