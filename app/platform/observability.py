"""관측성·운영 보조: request_id 미들웨어, /healthz, /readyz, /metrics 부착."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Awaitable, Callable

from fastapi import FastAPI, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.platform.cache.redis import get_redis

REQUEST_ID_HEADER = "X-Request-Id"

_access_log = logging.getLogger("pet_data_api.access")
_QUIET_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})


class AccessLogMiddleware(BaseHTTPMiddleware):
    """모든 요청의 진입·완료를 구조화 로그로 기록. 헬스·메트릭 경로는 DEBUG 레벨."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = getattr(request.state, "request_id", "-")
        rid_src = getattr(request.state, "request_id_source", "generated")
        path = request.url.path
        query = str(request.url.query) or "-"
        ip = request.client.host if request.client else "-"
        caller = request.headers.get("x-caller-service") or "-"
        quiet = path in _QUIET_PATHS

        log = _access_log.debug if quiet else _access_log.info
        log(
            "[%s] --> %s %s query=%s ip=%s caller=%s rid_src=%s",
            rid, request.method, path, query, ip, caller, rid_src,
        )

        t0 = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = int((time.monotonic() - t0) * 1000)
            _access_log.error("[%s] <-- 500 elapsed_ms=%d path=%s caller=%s", rid, elapsed, path, caller)
            raise

        elapsed = int((time.monotonic() - t0) * 1000)
        log("[%s] <-- %d elapsed_ms=%d path=%s caller=%s", rid, response.status_code, elapsed, path, caller)
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """모든 요청에 request_id 부여. 클라이언트가 헤더로 보내면 재사용, 없으면 생성.

    - request.state.request_id 로 라우터·로거에서 접근.
    - 응답에 동일한 X-Request-Id 헤더를 에코.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        if incoming:
            request_id = incoming
            request.state.request_id_source = "caller"
        else:
            request_id = uuid.uuid4().hex[:16]
            request.state.request_id_source = "generated"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def get_request_id(request: Request) -> str:
    """FastAPI Depends 용 헬퍼. 미들웨어가 항상 채워두므로 KeyError 가능성 없음."""
    return getattr(request.state, "request_id", "-")


def attach_observability(app: FastAPI) -> None:
    """앱에 미들웨어·헬스체크·메트릭을 부착. main.py 에서 한 번 호출."""
    # AccessLogMiddleware 를 먼저 등록해야 RequestIdMiddleware 가 outer(먼저 실행)가 되어
    # request_id 가 이미 설정된 상태에서 AccessLog 가 찍힌다.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/healthz", tags=["health"], summary="Liveness probe")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"], summary="Readiness probe (Redis)")
    async def readyz(response: Response):
        checks: dict[str, str] = {}
        ok = True

        try:
            r = get_redis()
            await r.ping()
            checks["redis"] = "ok"
        except Exception as e:
            ok = False
            checks["redis"] = f"error: {type(e).__name__}"

        if not ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ok" if ok else "degraded", "checks": checks}

    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["health"])
    except Exception:
        # prometheus 라이브러리 부재·초기화 실패 시 메트릭 없이 부팅
        pass
