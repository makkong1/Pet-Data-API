from contextlib import asynccontextmanager
import logging
import os
import re
import sys

from fastapi import FastAPI
from app.platform.cache.redis import get_redis
from app.platform.core.config import settings
from app.serving.api.collect import router as collect_router
from app.serving.api.facilities import router as facilities_router
from app.serving.api.popular import router as popular_router
from app.serving.api.trends import router as trends_router
from app.platform.scheduler.jobs import start_scheduler, stop_scheduler
from app.platform.observability import attach_observability

_log_main = logging.getLogger(__name__)


def _configure_logging() -> None:
    """app.* 와 pet_data_api.* 에 stderr Handler 를 붙임 — 기본 uvicorn 설정만으로는 이 로그가 안 보일 때가 많음."""
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    fmt = os.environ.get("LOG_FMT") or "%(asctime)s %(levelname)-8s %(name)s %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    for branch in ("app", "pet_data_api"):
        log = logging.getLogger(branch)
        log.handlers[:] = []
        log.setLevel(level)
        stderr_h = logging.StreamHandler(sys.stderr)
        stderr_h.setLevel(level)
        stderr_h.setFormatter(formatter)
        log.addHandler(stderr_h)
        log.propagate = False

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(level)


_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _redis_log_peer(url: str) -> str:
    """패스워드 제외: 확인용 호스트 경로만."""
    idx = url.rfind("@")
    return url[idx + 1 :] if idx != -1 else url


async def _startup_checks() -> None:
    ah = getattr(settings, "ADMIN_API_KEY_HASH", "") or ""
    if not _HEX64.fullmatch(ah.strip()):
        _log_main.warning(
            "ADMIN_API_KEY_HASH must be exactly 64 hex chars (SHA-256). "
            "Current length=%s — admin routes will reject keys until fixed.",
            len(ah.strip().replace(" ", "")),
        )

    try:
        await get_redis().ping()
        _log_main.info(
            "Startup: Redis OK (peer=%s). If `/collect/trigger` still shows no writes, "
            "check NAVER_* and application logs.",
            _redis_log_peer(settings.REDIS_URL),
        )
    except Exception as exc:
        _log_main.warning(
            "Startup: Redis ping FAILED (peer=%s): %s — `/readyz` degraded; trends/popular/collect Redis writes fail.",
            _redis_log_peer(settings.REDIS_URL),
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    await _startup_checks()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Popularity Intelligence API (Pet Data API)",
    description=(
        "Naver 블로그 기반 반려동물 서비스 인기도 API "
        "(Popularity intelligence from blog mentions)"
    ),
    lifespan=lifespan,
)
attach_observability(app)
app.include_router(facilities_router)
app.include_router(popular_router)
app.include_router(collect_router)
app.include_router(trends_router)
