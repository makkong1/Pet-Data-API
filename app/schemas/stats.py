from pydantic import BaseModel


class SummaryResponse(BaseModel):
    type: str
    region_city: str
    region_district: str
    count: int
