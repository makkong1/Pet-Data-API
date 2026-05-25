# pet-data-api

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)

Naver 블로그 기반 **트렌드 키워드** · **인기 시설** 데이터를 수집해 두 가지 형태로 제공합니다.

| 제공 방식 | 소비자 | 진입점 |
|---|---|---|
| FastAPI HTTP | Petory recommendation 도메인 | `GET /popular/{context}`, `GET /trends/{category}` |
| Python batch CLI | Spring locationservice DB | `python cli.py popular --output <path>` |

PostgreSQL 없음. 영속 상태는 Redis(서버 모드)와 CLI 출력 파일뿐입니다.

---

## Quick start

### 서버 (FastAPI)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# .env 설정 후 (아래 환경변수 참고)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger: `http://localhost:8000/docs`  
Redis가 떠 있어야 `/readyz` 및 데이터 조회가 정상입니다.

### 배치 CLI

```bash
source venv/bin/activate
python cli.py popular --output /data/popular.json
# 특정 컨텍스트만
python cli.py popular --output /data/grooming.json --contexts grooming hospital
```

출력 파일: `LocationImportDto` 배열 JSON → Spring `POST /api/admin/location/import` 또는 파일 경로 설정으로 자동 import.

---

## 환경변수 (.env)

```
API_KEY_HASH=<sha256 hex>
ADMIN_API_KEY_HASH=<sha256 hex>
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
REDIS_URL=redis://localhost:6379/0
NAVER_TIMEOUT_MS=10000
```

키 해시 생성:
```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print(k, hashlib.sha256(k.encode()).hexdigest())"
```

---

## API 엔드포인트

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| GET | `/healthz` | 없음 | Liveness |
| GET | `/readyz` | 없음 | Redis ping |
| GET | `/metrics` | 없음 | Prometheus |
| GET | `/popular/{context}` | 일반/관리자 | Redis 인기 시설 목록 |
| GET | `/trends/{category}` | 일반/관리자 | Redis 트렌드 키워드 |
| POST | `/collect/trigger` | 관리자 | 수동 배치 실행 |

컨텍스트: `grooming hospital supplies pharmacy cafe pension restaurant boarding hotel`

---

## 스케줄 (APScheduler, 로컬 시각)

| 시각 | 작업 |
|---|---|
| 18:00 | `run_trend_collection` → Redis `trends:{category}` |
| 18:10 | `run_popular_collection` → Redis `popular:{context}` |

`max_instances=1` 중복 실행 방지. Docker/클라우드 배포 시 `Asia/Seoul` 타임존 명시 필요.

---

## 테스트

```bash
source venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

---

## 문서

| 문서 | 경로 |
|---|---|
| 아키텍처 | [`docs/분析/ARCHITECTURE.md`](docs/분析/ARCHITECTURE.md) |
| Petory location 도메인 | [`docs/분析/PETORY-LOCATION-DOMAIN.md`](docs/분析/PETORY-LOCATION-DOMAIN.md) |
| Petory recommendation 도메인 | [`docs/분析/PETORY-RECOMMENDATION-DOMAIN.md`](docs/분析/PETORY-RECOMMENDATION-DOMAIN.md) |
| 코드 리뷰 이슈 | [`docs/superpowers/specs/2026-05-25-code-review-findings.md`](docs/superpowers/specs/2026-05-25-code-review-findings.md) |
