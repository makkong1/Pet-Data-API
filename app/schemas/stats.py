from datetime import date
from pydantic import BaseModel


class RegionStatResponse(BaseModel):
    region: str
    date: date
    total_count: int
    adopted_count: int
    euthanized_count: int


class TrendResponse(BaseModel):
    region: str
    year: int
    month: int
    total_count: int
    adopted_count: int
    euthanized_count: int
