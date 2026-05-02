from pydantic import BaseModel, Field


class SummaryResponse(BaseModel):
    type: str = Field(..., description="시설 유형 (Facility type)")
    region_city: str = Field(..., description="시·도 (City)")
    region_district: str = Field(..., description="시·군·구 (District)")
    count: int = Field(..., description="건수 (Count)")
