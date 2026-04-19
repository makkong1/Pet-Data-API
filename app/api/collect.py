from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_admin_key
from app.collector.runner import run_collection

router = APIRouter(prefix="/collect", tags=["admin"])


@router.post("/trigger")
async def trigger_collection(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin_key),
):
    logs = await run_collection(db)
    return [
        {
            "source": log.source,
            "status": log.status,
            "total_fetched": log.total_fetched,
            "total_saved": log.total_saved,
            "error_message": log.error_message,
            "started_at": log.started_at,
            "finished_at": log.finished_at,
        }
        for log in logs
    ]
