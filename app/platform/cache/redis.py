from datetime import datetime, timezone
from typing import Optional
import redis.asyncio as aioredis
from app.platform.core.config import settings

_redis: Optional[aioredis.Redis] = None

TREND_KEY = "trends:{category}:keywords"
UPDATED_KEY = "trends:{category}:updated_at"
TTL = 86400  # 24h


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def save_trend(category: str, keyword_counts: dict[str, int]) -> None:
    r = get_redis()
    key = TREND_KEY.format(category=category)
    updated_key = UPDATED_KEY.format(category=category)
    async with r.pipeline() as pipe:
        pipe.delete(key)
        if keyword_counts:
            pipe.zadd(key, keyword_counts)
        pipe.setex(updated_key, TTL, datetime.now(timezone.utc).isoformat())
        pipe.expire(key, TTL)
        await pipe.execute()


async def get_trend(category: str, limit: int = 20) -> list[tuple[str, float]]:
    r = get_redis()
    key = TREND_KEY.format(category=category)
    return await r.zrange(key, 0, limit - 1, desc=True, withscores=True)


async def get_updated_at(category: str) -> Optional[str]:
    r = get_redis()
    return await r.get(UPDATED_KEY.format(category=category))
