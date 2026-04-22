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
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    model_config = {"env_file": ".env"}


settings = Settings()
