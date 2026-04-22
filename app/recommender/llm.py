from typing import Optional
import httpx
from app.core.config import settings

OLLAMA_CHAT_PATH = "/api/chat"


async def generate_recommendation(prompt: str) -> Optional[str]:
    """Ollama llama3에 프롬프트 전송 → 추천 텍스트 반환. 실패 시 None."""
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "너는 반려동물 전문 추천 어시스턴트야. "
                    "반드시 한국어로, 3문장 이내로 간결하게 추천해. "
                    "불필요한 서론 없이 바로 추천 내용만 말해. "
                    "반드시 제공된 시설 목록에 있는 시설만 언급해. "
                    "목록에 없는 시설명은 절대 만들어내지 마."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}{OLLAMA_CHAT_PATH}",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
    except Exception:
        return None
