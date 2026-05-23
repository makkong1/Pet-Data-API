from typing import Optional
from pydantic import BaseModel


class PopularEntry(BaseModel):
    name: str
    mention_count: int
    avg_freshness: float
    score: float
    # Naver 로컬 검색으로 보강된 위치 정보 (없으면 None)
    address: Optional[str] = None
    road_address: Optional[str] = None
    map_x: Optional[str] = None
    map_y: Optional[str] = None
    telephone: Optional[str] = None
