import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel, Field

from app.ingestion.runner import run_popular_collection, run_trend_collection
from app.platform.core.auth import require_admin_key
from app.platform.observability import get_request_id

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/collect", tags=["관리자 (Admin)"])


class CollectRequest(BaseModel):
    targets: list[Literal["popular", "trends"]] = Field(
        ...,
        min_length=1,
        description="실행할 배치: popular, trends 또는 둘 다",
    )


@router.post(
    "/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="수집 실행 (Trigger collection)",
    description="popular 또는 trends 배치를 백그라운드로 즉시 실행합니다. 관리자 API 키 필요.",
    response_model=dict,
)
async def trigger_collection(
    request: Request,
    background_tasks: BackgroundTasks,
    body: CollectRequest,
    _: None = Depends(require_admin_key),
):
    rid = get_request_id(request)
    _log.info("[%s] trigger_collection targets=%s", rid, body.targets)
    dedup = list(dict.fromkeys(body.targets))
    for target in dedup:
        if target == "popular":
            background_tasks.add_task(run_popular_collection)
        elif target == "trends":
            background_tasks.add_task(run_trend_collection)
    return {"message": "collection started", "targets": dedup}
