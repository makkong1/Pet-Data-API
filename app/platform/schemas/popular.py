from pydantic import BaseModel


class PopularEntry(BaseModel):
    name: str
    mention_count: int
    avg_freshness: float
    score: float
