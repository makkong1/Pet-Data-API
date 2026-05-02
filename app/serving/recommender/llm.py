from typing import Optional
import httpx
from app.platform.core.config import settings

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
                    "이메시지에 나온 '주변 시설' 목록에 있는 상호(이름)만 인용해. "
                    "목록에 없는 업장명·영문 가게 이름·지어낸 브랜드는 절대 쓰지 마. "
                    "목록이 비어 있으면 한 문장으로 '시설 정보가 없다'고만 말해."
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
