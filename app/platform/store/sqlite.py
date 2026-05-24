import aiosqlite
import logging
from pathlib import Path
from app.platform.core.config import settings

_log = logging.getLogger(__name__)


async def init_db() -> None:
    path = Path(settings.SQLITE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS raw_posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       TEXT    NOT NULL,
                source       TEXT    NOT NULL,
                pipeline     TEXT    NOT NULL,
                category     TEXT    NOT NULL,
                query        TEXT    NOT NULL,
                link         TEXT    NOT NULL,
                title        TEXT,
                description  TEXT,
                postdate     TEXT,
                author_name  TEXT,
                collected_at TEXT    NOT NULL,
                UNIQUE(link)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_rp_run    ON raw_posts(run_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_rp_source ON raw_posts(source, pipeline, category)"
        )
        await db.commit()
    _log.info("sqlite init_db ok path=%s", path)


async def save_posts(
    records: list,
    run_id: str,
    pipeline: str,
    category: str,
    query: str,
    collected_at: str,
) -> int:
    if not records:
        return 0

    rows = [
        (
            run_id, r.source, pipeline, category, query,
            r.link, r.title, r.description, r.postdate,
            r.author_name, collected_at,
        )
        for r in records
    ]
    path = Path(settings.SQLITE_PATH)
    async with aiosqlite.connect(path) as db:
        await db.executemany(
            """
            INSERT OR IGNORE INTO raw_posts
                (run_id, source, pipeline, category, query, link,
                 title, description, postdate, author_name, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        await db.commit()
    inserted = len(rows)
    _log.info(
        "sqlite save_posts pipeline=%s category=%s source_sample=%s rows=%d",
        pipeline, category,
        records[0].source if records else "-",
        inserted,
    )
    return inserted
