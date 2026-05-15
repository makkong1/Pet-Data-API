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
    include_copy: bool = Field(
        False,
        description=(
            "LLM 추천 카피 포함 여부 (false 기본). false 면 규칙 기반 카피만 생성하고 p95 < 500ms. "
            "true 면 Ollama 호출까지 동기 대기. 카피만 비동기로 받으려면 별도 POST /recommend/copy 사용."
        ),
    )


class FacilityItem(BaseModel):
    name: str = Field(..., description="시설명 (Name)")
    distance_m: int = Field(..., description="거리 m (Distance meters)")
    address: str = Field(..., description="주소 (Address)")
    lat: Optional[float] = Field(None, description="위도 (Latitude)")
    lng: Optional[float] = Field(None, description="경도 (Longitude)")
    mention_count: int = Field(0, description="블로그 멘션 수 (0=없음·실패)")
    mention_score: float = Field(0.0, description="멘션 정규화 점수 [0.0-1.0]")
    source: str = Field("public", description="데이터 출처: public | kakao | public+kakao")
    score: float = Field(0.0, description="최종 랭킹 점수 [0.0-1.0]")
    reasons: List[str] = Field(
        default_factory=list,
        description="랭킹 기여 신호 라벨 (e.g. ['distance','trend_match:봄단발','pet_breed_match'])",
    )


class TrendKeyword(BaseModel):
    keyword: str = Field(..., description="키워드 (Keyword)")
    score: int = Field(..., description="가중치/점수 (Score)")


class RecommendResponse(BaseModel):
    context: str = Field(..., description="요청 맥락 (Requested context)")
    recommend_version: str = Field(
        "legacy",
        description="응답 파이프 버전 (legacy | grooming-mvp-v1 | hospital-mvp-v1 | supplies-mvp-v1)",
    )
    request_id: Optional[str] = Field(
        None,
        description="요청 추적 ID (X-Request-Id 와 동일, 콜백·로그 매핑용)",
    )
    facilities: List[FacilityItem] = Field(..., description="추천 시설 (Facilities)")
    trends: List[TrendKeyword] = Field(..., description="관련 트렌드 (Trend keywords)")
    recommendation: Optional[str] = Field(None, description="LLM 추천 문구 (LLM recommendation text)")
    generated_at: str = Field(..., description="생성 시각 ISO (Generated at, ISO 8601)")


class CopyFacility(BaseModel):
    name: str = Field(..., description="시설명")
    distance_m: Optional[int] = Field(None, description="거리 m (있으면 카피에 인용)")


class RecommendCopyRequest(BaseModel):
    context: str = Field(..., description="컨텍스트 (grooming|hospital|supplies)")
    request_id: Optional[str] = Field(
        None, description="원본 /recommend 응답의 request_id (로그 매핑용)"
    )
    facilities: List[CopyFacility] = Field(
        default_factory=list, description="카피에 인용할 시설 목록 (없으면 트렌드 기반 카피)"
    )
    trends: List[TrendKeyword] = Field(default_factory=list, description="트렌드 키워드")
    pet: Optional[PetInfo] = Field(None, description="반려 정보")


class RecommendCopyResponse(BaseModel):
    request_id: Optional[str] = Field(None, description="요청 추적 ID")
    recommendation: Optional[str] = Field(
        None, description="LLM 추천 카피 (LLM 다운·타임아웃 시 null)"
    )
    source: str = Field(
        "llm", description="카피 출처: llm | rule (LLM 실패 시 규칙 기반으로 폴백)"
    )
    generated_at: str = Field(..., description="생성 시각 ISO")
