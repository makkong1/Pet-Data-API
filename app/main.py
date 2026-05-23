from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.serving.api.collect import router as collect_router
from app.serving.api.trends import router as trends_router
from app.platform.scheduler.jobs import start_scheduler, stop_scheduler
from app.platform.observability import attach_observability


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.include_router(collect_router)
app.include_router(trends_router)
