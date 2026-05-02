from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_admin_key
from app.collector.runner import run_collection_by_scope

router = APIRouter(prefix="/collect", tags=["관리자 (Admin)"])


@router.post(
    "/trigger",
    summary="수집 실행 (Trigger collection)",
    description="공공 시설/트렌드 수집을 수동 실행. 관리자 API 키 필요. "
    "(Manual public-data or trend collection; requires admin API key.)",
)
async def trigger_collection(
    scope: str = Query(
        "facilities",
        pattern="^(facilities|trends|all)$",
        description="facilities | trends | all (What to collect)",
    ),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin_key),
):
    try:
        return await run_collection_by_scope(db, scope)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
