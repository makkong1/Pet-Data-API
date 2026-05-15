from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.serving.api.facilities import router as facilities_router
from app.serving.api.search import router as search_router
from app.serving.api.stats import router as stats_router
from app.serving.api.collect import router as collect_router
from app.serving.api.trends import router as trends_router
from app.serving.api.recommend import router as recommend_router
from app.serving.api.events import router as events_router
from app.platform.scheduler.jobs import start_scheduler, stop_scheduler
from app.platform.observability import attach_observability


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="반려동물 시설·트렌드 API (Pet Data API)",
    description=(
        "행안부 공공데이터 시설, 블로그 트렌드(Redis), 위치 기반 추천 "
        "(Government pet facility data, blog trends, location-based recommendations)"
    ),
    lifespan=lifespan,
)
attach_observability(app)
# /facilities/search 가 /facilities/{facility_id:int} 에 잡히지 않도록 search 먼저.
app.include_router(search_router)
app.include_router(facilities_router)
app.include_router(stats_router)
app.include_router(collect_router)
app.include_router(trends_router)
app.include_router(recommend_router)
app.include_router(events_router)
