# Step 1 — 설정 레이어

## 목적
`GROOMING_MVP_ENABLED` Feature flag 및 외부 API 타임아웃 상수를 Settings에 추가한다.  
이후 모든 Step이 이 상수를 import해서 사용한다.

## 배경
- SSOT: `docs/GROOMING-RECOMMEND-MVP.md` §1.1, §2.9
- 현재 `app/platform/core/config.py`는 `KAKAO_REST_API_KEY`, `NAVER_CLIENT_ID/SECRET` 등을 이미 갖고 있다.
- 타임아웃은 ms 단위로 정의하고 env로 덮어쓰기 가능하게 한다.

## 수정 대상 파일

### 1. `app/platform/core/config.py`

현재 코드:
```python
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
```

아래 3개 필드를 `KAKAO_REST_API_KEY` 아래에 추가한다:

```python
    # 그루밍 MVP Feature flag (§1.1)
    GROOMING_MVP_ENABLED: bool = False

    # HTTP 타임아웃 (ms) — §2.9
    NAVER_TIMEOUT_MS: int = 10_000
    KAKAO_TIMEOUT_MS: int = 8_000
```

`OLLAMA_BASE_URL`, `OLLAMA_MODEL`은 그대로 유지.

### 2. `.env.example`

파일 끝에 아래 블록을 추가한다:

```
# 그루밍 추천 MVP Feature flag (docs/GROOMING-RECOMMEND-MVP.md §1.1)
GROOMING_MVP_ENABLED=false

# 외부 API 타임아웃 (ms) — 운영 환경에서 덮어쓰기 가능 (§2.9)
NAVER_TIMEOUT_MS=10000
KAKAO_TIMEOUT_MS=8000
```

## 완료 기준 (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate

# Settings 로드 오류 없음 확인
python3 -c "
from app.platform.core.config import settings
assert hasattr(settings, 'GROOMING_MVP_ENABLED')
assert settings.GROOMING_MVP_ENABLED is False
assert settings.NAVER_TIMEOUT_MS == 10_000
assert settings.KAKAO_TIMEOUT_MS == 8_000
print('Step 1 AC passed')
"
```

## 주의
- 기존 필드 순서·이름 변경 금지.
- `Settings` 클래스 내 `model_config = {"env_file": ".env"}` 라인은 건드리지 않는다.
