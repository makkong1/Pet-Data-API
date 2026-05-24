import hashlib
import re
from typing import Annotated, Optional

from fastapi import Header, HTTPException, status
from app.platform.core.config import settings

_HEX64_PLAIN_HEADER = re.compile(r"^[0-9a-fA-F]{64}$")


def hash_key(key: str) -> str:
    """헤더/평문 공백·개행 때문에 401 나는 경우 방지."""
    return hashlib.sha256(key.strip().encode()).hexdigest()


def verify_key(key: str, hashed: str) -> bool:
    return hash_key(key) == hashed


def _looks_like_sha256_hex_plaintext(s: str) -> bool:
    """Plaintext key 헤더에 .env 의 SHA-256 hex(64) 를 그대로 넣는 실수 완화."""
    return bool(_HEX64_PLAIN_HEADER.fullmatch((s or "").strip()))


async def require_api_key(
    x_api_key: Annotated[
        Optional[str],
        Header(
            alias="X-API-Key",
            description="일반 또는 관리자 API 키 평문 (Plain API or admin key)",
        ),
    ] = None,
):
    """헤더 누락 시에는 FastAPI 기본값(422 Validation) 대신 401 으로 응답."""
    if x_api_key is None or not x_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if not (
        verify_key(x_api_key, settings.API_KEY_HASH)
        or verify_key(x_api_key, settings.ADMIN_API_KEY_HASH)
    ):
        if _looks_like_sha256_hex_plaintext(x_api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Invalid API Key: header looks like SHA-256 hex (API_KEY_HASH / ADMIN_API_KEY_HASH). "
                    "Send the matching plaintext API key instead of the digest."
                ),
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")


async def require_admin_key(
    x_api_key: Annotated[
        Optional[str],
        Header(
            alias="X-API-Key",
            description="관리자 API 키 평문 (Plain admin API key only)",
        ),
    ] = None,
):
    if x_api_key is None or not x_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if not verify_key(x_api_key, settings.ADMIN_API_KEY_HASH):
        if verify_key(x_api_key, settings.API_KEY_HASH):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")
        if _looks_like_sha256_hex_plaintext(x_api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Invalid API Key: header looks like SHA-256 hex (ADMIN_API_KEY_HASH). "
                    "Send the plaintext admin key, not the digest."
                ),
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
