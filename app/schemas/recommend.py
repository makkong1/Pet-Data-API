from typing import Optional, List
from pydantic import BaseModel, Field


class PetInfo(BaseModel):
    type: str          # "dog" | "cat" | "etc"
    breed: Optional[str] = None
    age: Optional[str] = None   # "3살", "5개월" 등 자유 형식


class RecommendRequest(BaseModel):
    lat: float = Field(..., description="사용자 위도")
    lng: float = Field(..., description="사용자 경도")
    context: str = Field(..., description="grooming | hospital | snack | food | clothes")
    radius_km: float = Field(3.0, ge=0.5, le=20.0)
    top_n: int = Field(5, ge=1, le=20)
    pet: Optional[PetInfo] = None


class FacilityItem(BaseModel):
    name: str
    distance_m: int
    address: str
    lat: Optional[float] = None
    lng: Optional[float] = None


class TrendKeyword(BaseModel):
    keyword: str
    score: int


class RecommendResponse(BaseModel):
    context: str
    facilities: List[FacilityItem]
    trends: List[TrendKeyword]
    recommendation: Optional[str]
    generated_at: str
