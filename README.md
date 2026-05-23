# pet-data-api

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)

네이버 블로그 검색으로 **카테고리별 트렌드 키워드**와 **컨텍스트별 인기 상호(Popularity)** 를 수집해 Redis에 두고, API로 제공하는 작은 FastAPI 서비스입니다. PostgreSQL·공공 API·추천(`POST /recommend`) 등은 포함하지 않습니다.

- 앱 진입점: [`app/main.py`](app/main.py)
- 라우터: [`app/serving/api/trends.py`](app/serving/api/trends.py), [`app/serving/api/popular.py`](app/serving/api/popular.py), [`app/serving/api/collect.py`](app/serving/api/collect.py)
- 배치 수집: [`app/ingestion/runner.py`](app/ingestion/runner.py)
- 레포의 `migrations/` SQL은 과거 레거시 스키마 참고용이며, 현재 앱 실행에 필요하지 않습니다.

---

## Quick start

프로젝트 루트에서:

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
# .env 에 NAVER_* , REDIS_URL , API 키 해시 등 설정 후 (상세는 docs/USAGE.md)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger: `http://localhost:8000/docs`
- Redis가 떠 있어야 `/readyz` 및 데이터 조회가 정상입니다.

---

## 기능 요약

1. **트렌드** — Naver 블로그 → 형태소(kiwipiepy) 집계 → Redis `trends:{category}:keywords` 등. **`GET /trends/{category}`** 로 조회.
2. **인기 상호(Popularity)** — 컨텍스트별 블로그 텍스트에서 상호 후보 추출·집계 → Redis `popular:{context}` (JSON 배열). **`GET /popular/{context}`** 로 조회.

---

## 스케줄 (로컬 시각)

[`app/platform/scheduler/jobs.py`](app/platform/scheduler/jobs.py)

| 시각 | 작업 |
|------|------|
| 18:00 | `run_trend_collection` |
| 18:10 | `run_popular_collection` |

`max_instances=1` 로 중복 실행을 막습니다. 타임존은 프로세스 로컬 시각 기준입니다.

---

## 문서

- [프로젝트 개요](docs/PROJECT-OVERVIEW.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [데이터·API 흐름](docs/분석/DATA-AND-API-FLOW.md)
- [실행·curl·환경변수](docs/USAGE.md)
- [Petory 연동](docs/PETORY-INTEGRATION.md)
- [변경 이력 (v3 및 이후)](docs/V3-CHANGES.md)

---

## 테스트

```bash
cd pet-data-api
source venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```
