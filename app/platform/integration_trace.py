"""Petory·기타 호출측 요청 추적용 구조 로그(JSON 아님, grep 용 문자열 일관 패턴).

access 미들웨어와 분리해서: 경로별 파라미터·Redis 키·반환 요약을 한 줄에 모은다.
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.requests import Request

_LOG = logging.getLogger("pet_data_api.petory_compat")


def inbound(request: Request, *, op: str, **fields: Any) -> None:
    client = "-"
    if request.client:
        client = getattr(request.client, "host", None) or "-"
    ua = (request.headers.get("user-agent") or "-").replace("\n", " ")[:160]
    rid = getattr(request.state, "request_id", "-")
    path = request.url.path
    query = request.url.query or "-"
    extra = " ".join(f"{k}={v!r}" for k, v in fields.items())
    _LOG.info("[%s][petory-compat] inbound %s path=%s query=%s client=%s ua_preview=%s %s",
              rid, op, path, query, client, ua, extra)


def outbound_redis_hit(
    request: Request,
    *,
    op: str,
    redis_key: str | None,
    status: str,
    **fields: Any,
) -> None:
    rid = getattr(request.state, "request_id", "-")
    extra = " ".join(f"{k}={v!r}" for k, v in fields.items())
    _LOG.info("[%s][petory-compat] outbound %s status=%s redis_key=%r %s",
              rid, op, status, redis_key, extra)
