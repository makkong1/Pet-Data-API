import hashlib
from fastapi import Header, HTTPException, status
from app.platform.core.config import settings


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_key(key: str, hashed: str) -> bool:
    return hash_key(key) == hashed


async def require_api_key(
    x_api_key: str = Header(
        ...,
        alias="X-API-Key",
        description="일반 또는 관리자 API 키 평문 (Plain API or admin key)",
    ),
):
    if not (
        verify_key(x_api_key, settings.API_KEY_HASH)
        or verify_key(x_api_key, settings.ADMIN_API_KEY_HASH)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")


async def require_admin_key(
    x_api_key: str = Header(
        ...,
        alias="X-API-Key",
        description="관리자 API 키 평문 (Plain admin API key only)",
    ),
):
    if not verify_key(x_api_key, settings.ADMIN_API_KEY_HASH):
        if verify_key(x_api_key, settings.API_KEY_HASH):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
