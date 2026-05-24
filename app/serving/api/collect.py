import asyncio
import logging
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.ingestion.runner import run_popular_collection, run_trend_collection
from app.platform import integration_trace
from app.platform.core.auth import require_admin_key
from app.platform.observability import get_request_id

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/collect", tags=["관리자 (Admin)"])


class CollectRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"targets": ["popular", "trends"]},
        }
    )
    targets: list[Literal["popular", "trends"]] = Field(
        ...,
        min_length=1,
        description="실행할 배치: popular, trends 또는 둘 다",
    )


class CollectTriggerResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "collection started",
                "targets": ["popular", "trends"],
                "request_id": "a1b2c3d4e5f67890",
                "results": None,
            }
        }
    )
    message: str
    targets: list[str]
    request_id: str
    results: Optional[dict[str, Any]] = Field(
        default=None,
        description="wait=true 동기 실행일 때만: popular/trends별 runner 반환값·오류 요약.",
    )


async def _run_popular_batch(request_id: str) -> None:
    _log.info("[%s] background popular START (run_popular_collection)", request_id)
    try:
        await run_popular_collection()
        _log.info("[%s] background popular DONE", request_id)
    except Exception:
        _log.exception("[%s] background popular FAILED", request_id)


async def _run_trends_batch(request_id: str) -> None:
    _log.info("[%s] background trends START (run_trend_collection)", request_id)
    try:
        await run_trend_collection()
        _log.info("[%s] background trends DONE", request_id)
    except Exception:
        _log.exception("[%s] background trends FAILED", request_id)


@router.post(
    "/trigger",
    responses={
        200: {
            "description": "동기 실행 완료 (?wait=true) — 결과는 `results` 필드 참고.",
        },
        202: {
            "description": (
                "백그라운드 실행 예약 (?wait=false 기본). "
                "uvicorn `--reload` 또는 프로세스 재시작이 겹치면 작업이 끊길 수 있음."
            ),
        },
    },
    summary="수집 실행 (Trigger collection)",
    description=(
        "popular 또는 trends 배치 실행. 기본값(`wait=false`): **즉시 202** + `BackgroundTasks`로 비동기 실행. "
        "`wait=true`(쿼리): **동기까지 끝난 뒤 200** + 응답에 `results` — "
        "**`uvicorn --reload`가 돌거나 파일 저장으로 워커가 재시작될 때** 백그라운드 작업이 끊기는 경우에 사용하세요.\n\n"
        "**관리자 평문 API 키** 필요 "
        "(`.env` 의 `ADMIN_API_KEY_HASH` 는 SHA-256 hex 이고, 헤더에는 그 해시에 대응하는 **평문 키**만 넣습니다).\n\n"
        "먼저 `GET /readyz` 로 Redis 가 `ok` 인지 확인하세요.\n\n"
        "Request body는 **유효한 JSON**이어야 합니다(객체는 반드시 `}` 로 닫기). "
        "예: 한 줄 `{\"targets\":[\"popular\",\"trends\"]}`. "
        "**응답의 `request_id`** 로 터미널 로그 `[...]` 과 대조하면 됩니다."
    ),
    response_model=CollectTriggerResponse,
)
async def trigger_collection(
    _: Annotated[None, Depends(require_admin_key)],
    response: Response,
    request: Request,
    background_tasks: BackgroundTasks,
    body: Annotated[
        CollectRequest,
        Body(
            openapi_examples={
                "both": {
                    "summary": "popular + trends",
                    "value": {"targets": ["popular", "trends"]},
                },
                "trends_only": {
                    "summary": "trends만",
                    "value": {"targets": ["trends"]},
                },
                "popular_only": {
                    "summary": "popular만",
                    "value": {"targets": ["popular"]},
                },
            },
        ),
    ],
    wait: Annotated[
        bool,
        Query(
            description=(
                "true: 같은 요청 안에서 배치가 끝날 때까지 대기 후 200 및 results 반환 "
                "(reload로 백그라운드가 취소되는 로컬 개발에 유리). "
                "false: 202 Accepted 후 BackgroundTasks 실행(기본)."
            ),
        ),
    ] = False,
):
    rid = get_request_id(request)
    dedup = list(dict.fromkeys(body.targets))
    integration_trace.inbound(
        request,
        op="collect_trigger",
        targets=dedup,
        wait=wait,
    )
    if wait:
        response.status_code = status.HTTP_200_OK
        _log.info("[%s] trigger_collection wait=true targets=%s (in-request)", rid, dedup)
        gathered: list = []
        order: list[str] = []
        for target in dedup:
            if target == "popular":
                order.append("popular")
                gathered.append(run_popular_collection())
            elif target == "trends":
                order.append("trends")
                gathered.append(run_trend_collection())
        outs = await asyncio.gather(*gathered, return_exceptions=True)
        results_out: dict[str, Any] = {}
        for name, out in zip(order, outs):
            if isinstance(out, BaseException):
                _log.error("[%s] blocking %s FAILED: %r", rid, name, out)
                results_out[name] = {"status": "error", "detail": repr(out)}
            else:
                _log.info("[%s] blocking %s DONE", rid, name)
                results_out[name] = {"status": "ok", "detail": out}
        ok_all = all(v.get("status") == "ok" for v in results_out.values())
        integration_trace.outbound_redis_hit(
            request,
            op="collect_trigger",
            redis_key=None,
            status=("ok" if ok_all else "partial_or_error"),
            wait=True,
            targets=dedup,
            preview={k: v.get("status") for k, v in results_out.items()},
        )
        return CollectTriggerResponse(
            message="collection finished",
            targets=dedup,
            request_id=rid,
            results=results_out,
        )

    response.status_code = status.HTTP_202_ACCEPTED
    _log.info("[%s] trigger_collection accepted targets=%s (scheduling background)", rid, dedup)
    for target in dedup:
        if target == "popular":
            background_tasks.add_task(_run_popular_batch, rid)
        elif target == "trends":
            background_tasks.add_task(_run_trends_batch, rid)
    integration_trace.outbound_redis_hit(
        request,
        op="collect_trigger",
        redis_key=None,
        status="accepted",
        mode="background",
        targets=dedup,
        note="see [ingestion-digest] logs when runner finishes",
    )
    return CollectTriggerResponse(message="collection started", targets=dedup, request_id=rid)
