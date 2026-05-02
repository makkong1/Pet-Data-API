from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.platform.core.database import get_db
from app.platform.core.auth import require_admin_key
from app.ingestion.runner import run_collection_by_scope

router = APIRouter(prefix="/collect", tags=["관리자 (Admin)"])

_ALLOWED_SCOPES = frozenset({"facilities", "trends", "all"})


def collect_scope(
    scope: str = Query(
        default="facilities",
        description="facilities | trends | all (What to collect)",
    ),
) -> str:
    """Swagger에서 scope를 비우면 빈 문자열이 와 pattern/Literal 검증이 422로 터지므로, 공백·빈 값은 기본값으로 취급."""
    s = (scope or "").strip() or "facilities"
    if s not in _ALLOWED_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "type": "enum",
                    "loc": ["query", "scope"],
                    "msg": "must be one of: facilities, trends, all",
                    "input": s,
                }
            ],
        )
    return s


@router.post(
    "/trigger",
    summary="수집 실행 (Trigger collection)",
    description="공공 시설/트렌드 수집을 수동 실행. 관리자 API 키 필요. "
    "(Manual public-data or trend collection; requires admin API key.)",
    response_model=dict,
)
async def trigger_collection(
    scope: str = Depends(collect_scope),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin_key),
):
    try:
        return await run_collection_by_scope(db, scope)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
