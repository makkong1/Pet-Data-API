"""공공 데이터의 business_type / specialty 를 facility_tags 로 비정규화 백필.

검색 깊이 확보용 최초 시드. 멱등(같은 (facility_id, tag, source) 는 ON CONFLICT DO NOTHING).
태그는 콤마·슬래시·세미콜론·공백으로 잘라 trim·lowercase 후 INSERT.
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.platform.core.config import settings


_SPLIT_RE = re.compile(r"[,/;·∙\s]+")


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    tags = [t.strip().lower() for t in _SPLIT_RE.split(raw)]
    return [t for t in tags if t and len(t) <= 50]


async def _seed_business_tags(db: AsyncSession) -> int:
    result = await db.execute(
        text(
            "SELECT bd.facility_id, bd.business_type "
            "FROM business_details bd "
            "WHERE bd.business_type IS NOT NULL AND bd.business_type <> ''"
        )
    )
    inserted = 0
    for row in result.mappings().all():
        for tag in _split_tags(row["business_type"]):
            await db.execute(
                text(
                    "INSERT INTO facility_tags (facility_id, tag, source) "
                    "VALUES (:fid, :tag, 'public') "
                    "ON CONFLICT (facility_id, tag, source) DO NOTHING"
                ),
                {"fid": row["facility_id"], "tag": tag},
            )
            inserted += 1
    return inserted


async def _seed_hospital_tags(db: AsyncSession) -> int:
    result = await db.execute(
        text(
            "SELECT hd.facility_id, hd.specialty "
            "FROM hospital_details hd "
            "WHERE hd.specialty IS NOT NULL AND hd.specialty <> ''"
        )
    )
    inserted = 0
    for row in result.mappings().all():
        for tag in _split_tags(row["specialty"]):
            await db.execute(
                text(
                    "INSERT INTO facility_tags (facility_id, tag, source) "
                    "VALUES (:fid, :tag, 'public') "
                    "ON CONFLICT (facility_id, tag, source) DO NOTHING"
                ),
                {"fid": row["facility_id"], "tag": tag},
            )
            inserted += 1
    return inserted


async def run() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        biz = await _seed_business_tags(db)
        hos = await _seed_hospital_tags(db)
        await db.commit()
    print(f"seeded — business={biz} hospital={hos} total={biz + hos}")


if __name__ == "__main__":
    asyncio.run(run())
