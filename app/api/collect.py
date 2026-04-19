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
    return await run_collection(db)
