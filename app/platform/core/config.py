from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    API_KEY_HASH: str
    ADMIN_API_KEY_HASH: str
    PUBLIC_DATA_API_KEY: str
    HOSPITAL_API_KEY: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    REDIS_URL: str = "redis://localhost:6379/0"
    NAVER_MAP_CLIENT_ID: str = ""
    NAVER_MAP_CLIENT_SECRET: str = ""
    KAKAO_REST_API_KEY: str = ""
    # 그루밍 MVP Feature flag (docs/GROOMING-RECOMMEND-MVP.md §1.1)
    GROOMING_MVP_ENABLED: bool = False
    # HTTP 타임아웃 (ms) — §2.9
    NAVER_TIMEOUT_MS: int = 10_000
    KAKAO_TIMEOUT_MS: int = 8_000
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    model_config = {"env_file": ".env"}


settings = Settings()
