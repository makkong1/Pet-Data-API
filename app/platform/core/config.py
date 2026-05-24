from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 프로젝트 루트의 .env 고정 로드(uvicorn 시작 cwd 가 달라도 동일 설정).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DOTENV = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    API_KEY_HASH: str
    ADMIN_API_KEY_HASH: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    REDIS_URL: str = "redis://localhost:6379/0"
    NAVER_TIMEOUT_MS: int = 10_000
    SQLITE_PATH: str = "data/raw_posts.db"

    model_config = SettingsConfigDict(
        env_file=_DOTENV,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("API_KEY_HASH", "ADMIN_API_KEY_HASH", mode="before")
    @classmethod
    def _trim_hash_fields(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


settings = Settings()
