import logging
import httpx
from app.platform.core.config import settings

_log = logging.getLogger(__name__)


async def ingest_candidates(dtos: list[dict]) -> int:
    """place_candidates 배치 적재. 성공 시 저장된 수 반환, 실패 시 0."""
    if not dtos:
        return 0

    payload = {"candidates": dtos}
    headers = {}
    if settings.PETORY_INGEST_TOKEN:
        headers["Authorization"] = f"Bearer {settings.PETORY_INGEST_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(settings.PETORY_INGEST_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            saved = data.get("saved", 0)
            _log.info("petory_ingest ok sent=%d saved=%d", len(dtos), saved)
            return saved
    except Exception as exc:
        _log.error("petory_ingest failed sent=%d err=%s", len(dtos), exc)
        return 0
