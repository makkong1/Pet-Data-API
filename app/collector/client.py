import asyncio
import httpx

BASE_URL = "http://apis.data.go.kr/1543061/abandonmentPublicSrvc/abandonmentPublic"
RETRY_DELAYS = [1, 2, 4]


async def fetch_abandoned_animals(service_key: str, page: int = 1, num_of_rows: int = 1000) -> dict:
    params = {
        "serviceKey": service_key,
        "pageNo": page,
        "numOfRows": num_of_rows,
        "_type": "json",
    }
    last_error = None
    for delay in [0] + RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(BASE_URL, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            last_error = e
    raise last_error
