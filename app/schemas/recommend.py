from typing import Optional, List
from pydantic import BaseModel, Field


class PetInfo(BaseModel):
    type: str = Field(..., description="반려 종류 (Pet species: dog | cat | etc)")
    breed: Optional[str] = Field(None, description="품종 (Breed)")
    age: Optional[str] = Field(None, description="나이 표현 (Age, free text e.g. 3살)")


class RecommendRequest(BaseModel):
    lat: float = Field(..., description="위도 (Latitude)")
    lng: float = Field(..., description="경도 (Longitude)")
    context: str = Field(
        ...,
        description="맥락 (Context: grooming | hospital | supplies; legacy: snack | food | clothes)",
    )
    radius_km: float = Field(3.0, ge=0.5, le=20.0, description="검색 반경 km (Search radius km)")
    top_n: int = Field(5, ge=1, le=20, description="반환 시설 수 상한 (Max facilities)")
    pet: Optional[PetInfo] = Field(None, description="반려 정보 (Optional pet profile)")


class FacilityItem(BaseModel):
    name: str = Field(..., description="시설명 (Name)")
    distance_m: int = Field(..., description="거리 m (Distance meters)")
    address: str = Field(..., description="주소 (Address)")
    lat: Optional[float] = Field(None, description="위도 (Latitude)")
    lng: Optional[float] = Field(None, description="경도 (Longitude)")


class TrendKeyword(BaseModel):
    keyword: str = Field(..., description="키워드 (Keyword)")
    score: int = Field(..., description="가중치/점수 (Score)")


class RecommendResponse(BaseModel):
    context: str = Field(..., description="요청 맥락 (Requested context)")
    facilities: List[FacilityItem] = Field(..., description="추천 시설 (Facilities)")
    trends: List[TrendKeyword] = Field(..., description="관련 트렌드 (Trend keywords)")
    recommendation: Optional[str] = Field(None, description="LLM 추천 문구 (LLM recommendation text)")
    generated_at: str = Field(..., description="생성 시각 ISO (Generated at, ISO 8601)")
