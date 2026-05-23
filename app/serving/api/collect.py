import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from app.platform.core.auth import require_admin_key
from app.platform.observability import get_request_id
from app.ingestion.runner import run_trend_collection

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/collect", tags=["관리자 (Admin)"])


async def _run_trends_background() -> None:
    try:
        result = await run_trend_collection()
        _log.info("background trend collection done result=%s", result)
    except Exception as e:
        _log.error("background trend collection failed error=%s", e)


@router.post(
    "/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="수집 실행 (Trigger collection)",
    response_model=dict,
)
async def trigger_collection(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_admin_key),
):
    rid = get_request_id(request)
    _log.info("[%s] trigger_collection -> trends background", rid)
    background_tasks.add_task(_run_trends_background)
    return {"message": "collection started", "targets": ["trends"]}
