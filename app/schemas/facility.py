from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel


class FacilityResponse(BaseModel):
    id: int
    source_id: str
    type: str
    name: str
    status: str
    address: str
    region_city: str
    region_district: str
    phone: Optional[str]
    collected_at: datetime

    model_config = {"from_attributes": True}


class FacilityListResponse(BaseModel):
    items: List[FacilityResponse]
    next_cursor: Optional[int]
    has_next: bool


class FacilityDetailResponse(BaseModel):
    id: int
    source_id: str
    type: str
    name: str
    status: str
    address: str
    region_city: str
    region_district: str
    phone: Optional[str]
    collected_at: datetime
    details: Dict[str, Any]

    model_config = {"from_attributes": True}
