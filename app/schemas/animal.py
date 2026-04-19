from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class AnimalResponse(BaseModel):
    id: int
    notice_no: str
    animal_type: Optional[str]
    breed: Optional[str]
    age: Optional[str]
    gender: Optional[str]
    region: Optional[str]
    shelter_name: Optional[str]
    status: Optional[str]
    notice_date: Optional[date]
    collected_at: datetime

    model_config = {"from_attributes": True}


class AnimalListResponse(BaseModel):
    items: list[AnimalResponse]
    next_cursor: Optional[int]
    has_next: bool
