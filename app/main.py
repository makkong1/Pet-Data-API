from fastapi import FastAPI
from app.api.animals import router as animals_router
from app.api.stats import router as stats_router

app = FastAPI(title="Pet Data API")
app.include_router(animals_router)
app.include_router(stats_router)
