import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from app.platform.core.database import AsyncSessionLocal
from app.platform.core.auth import require_admin_key
from app.platform.observability import get_request_id
from app.ingestion.runner import run_collection_by_scope

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/collect", tags=["관리자 (Admin)"])

_ALLOWED_SCOPES = frozenset({"facilities", "trends", "all"})


async def _run_in_background(scope: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            result = await run_collection_by_scope(db, scope)
        _log.info("background collection done scope=%s result=%s", scope, result)
    except Exception as e:
        _log.error("background collection failed scope=%s error=%s", scope, e)


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
    status_code=status.HTTP_202_ACCEPTED,
    summary="수집 실행 (Trigger collection)",
    description="공공 시설/트렌드 수집을 백그라운드로 실행. 즉시 202 반환. 관리자 API 키 필요. "
    "(Starts collection in background, returns 202 immediately; requires admin API key.)",
    response_model=dict,
)
async def trigger_collection(
    request: Request,
    background_tasks: BackgroundTasks,
    scope: str = Depends(collect_scope),
    _: None = Depends(require_admin_key),
):
    rid = get_request_id(request)
    _log.info("[%s] trigger_collection scope=%s -> 백그라운드 수집 예약", rid, scope)
    background_tasks.add_task(_run_in_background, scope)
    return {"status": "accepted", "scope": scope}
