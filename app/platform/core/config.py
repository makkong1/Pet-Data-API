from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_KEY_HASH: str
    ADMIN_API_KEY_HASH: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    REDIS_URL: str = "redis://localhost:6379/0"
    NAVER_TIMEOUT_MS: int = 10_000

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
