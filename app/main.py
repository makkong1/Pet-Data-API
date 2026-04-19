from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.animals import router as animals_router
from app.api.stats import router as stats_router
from app.api.collect import router as collect_router
from app.scheduler.jobs import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Pet Data API", lifespan=lifespan)
app.include_router(animals_router)
app.include_router(stats_router)
app.include_router(collect_router)
