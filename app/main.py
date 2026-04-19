from fastapi import FastAPI
from app.api.animals import router as animals_router

app = FastAPI(title="Pet Data API")
app.include_router(animals_router)
