import asyncio
import httpx
from typing import Optional

RETRY_DELAYS = [1, 2, 4]


async def fetch_public_api(url: str, params: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 30) -> dict:
    last_error: Optional[Exception] = None
    for delay in [0] + RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            last_error = e
    raise last_error
