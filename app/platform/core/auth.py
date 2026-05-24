import hashlib
import logging
import re
from typing import Annotated, Optional

from fastapi import Header, HTTPException, Request, status
from app.platform.core.config import settings

_log = logging.getLogger(__name__)
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
    request: Request,
    x_api_key: Annotated[
        Optional[str],
        Header(
            alias="X-API-Key",
            description="일반 또는 관리자 API 키 평문 (Plain API or admin key)",
        ),
    ] = None,
):
    """헤더 누락 시에는 FastAPI 기본값(422 Validation) 대신 401 으로 응답."""
    rid = getattr(request.state, "request_id", "-")
    path = request.url.path

    if x_api_key is None or not x_api_key.strip():
        _log.warning("[%s] auth 401 reason=missing_header path=%s", rid, path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    is_admin = verify_key(x_api_key, settings.ADMIN_API_KEY_HASH)
    is_user = verify_key(x_api_key, settings.API_KEY_HASH)

    if is_admin or is_user:
        key_type = "admin" if is_admin else "user"
        _log.debug("[%s] auth ok key_type=%s path=%s", rid, key_type, path)
        return

    if _looks_like_sha256_hex_plaintext(x_api_key):
        _log.warning("[%s] auth 401 reason=sent_hash_as_plaintext path=%s", rid, path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid API Key: header looks like SHA-256 hex (API_KEY_HASH / ADMIN_API_KEY_HASH). "
                "Send the matching plaintext API key instead of the digest."
            ),
        )

    _log.warning("[%s] auth 401 reason=invalid_key path=%s", rid, path)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")


async def require_admin_key(
    request: Request,
    x_api_key: Annotated[
        Optional[str],
        Header(
            alias="X-API-Key",
            description="관리자 API 키 평문 (Plain admin API key only)",
        ),
    ] = None,
):
    rid = getattr(request.state, "request_id", "-")
    path = request.url.path

    if x_api_key is None or not x_api_key.strip():
        _log.warning("[%s] auth 401 reason=missing_header path=%s", rid, path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    if verify_key(x_api_key, settings.ADMIN_API_KEY_HASH):
        _log.debug("[%s] auth ok key_type=admin path=%s", rid, path)
        return

    if verify_key(x_api_key, settings.API_KEY_HASH):
        _log.warning("[%s] auth 403 reason=user_key_on_admin_path path=%s", rid, path)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin key required")

    if _looks_like_sha256_hex_plaintext(x_api_key):
        _log.warning("[%s] auth 401 reason=sent_hash_as_plaintext path=%s", rid, path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid API Key: header looks like SHA-256 hex (ADMIN_API_KEY_HASH). "
                "Send the plaintext admin key, not the digest."
            ),
        )

    _log.warning("[%s] auth 401 reason=invalid_key path=%s", rid, path)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
