from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class FacilityResponse(BaseModel):
    id: int = Field(..., description="내부 ID (Internal id)")
    source_id: str = Field(..., description="공공데이터 소스 ID (Source id)")
    type: str = Field(..., description="유형 (Type, e.g. BUSINESS | HOSPITAL)")
    name: str = Field(..., description="상호 (Name)")
    status: str = Field(..., description="영업 상태 (Status)")
    address: str = Field(..., description="주소 (Address)")
    region_city: str = Field(..., description="시·도 (City)")
    region_district: str = Field(..., description="시·군·구 (District)")
    phone: Optional[str] = Field(None, description="전화 (Phone)")
    collected_at: datetime = Field(..., description="수집 시각 (Collected at)")

    model_config = {"from_attributes": True}


class FacilityListResponse(BaseModel):
    items: List[FacilityResponse] = Field(..., description="시설 목록 (Items)")
    next_cursor: Optional[int] = Field(None, description="다음 페이지 커서 (Next cursor)")
    has_next: bool = Field(..., description="추가 페이지 존재 (Has next page)")


class FacilityDetailResponse(BaseModel):
    id: int = Field(..., description="내부 ID (Internal id)")
    source_id: str = Field(..., description="공공데이터 소스 ID (Source id)")
    type: str = Field(..., description="유형 (Type)")
    name: str = Field(..., description="상호 (Name)")
    status: str = Field(..., description="영업 상태 (Status)")
    address: str = Field(..., description="주소 (Address)")
    region_city: str = Field(..., description="시·도 (City)")
    region_district: str = Field(..., description="시·군·구 (District)")
    phone: Optional[str] = Field(None, description="전화 (Phone)")
    collected_at: datetime = Field(..., description="수집 시각 (Collected at)")
    details: Dict[str, Any] = Field(..., description="유형별 상세 (Type-specific details)")

    model_config = {"from_attributes": True}
