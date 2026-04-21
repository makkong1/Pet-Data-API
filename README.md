# pet-data-api

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)

> 공공데이터 + 네이버 블로그 분석 기반 반려동물 시설·트렌드 REST API

---

## 프로젝트 소개

반려동물 관련 정보를 두 가지 방식으로 수집합니다.

- **공공데이터 (행안부)**: 전국 동물미용업·동물병원 공식 등록 정보를 매일 자동 수집해 DB에 적재
- **네이버 블로그 API**: 간식·사료·미용·병원·옷 카테고리별 블로그 텍스트를 수집, 형태소 분석으로 인기 키워드를 추출해 Redis에 캐싱

Java/Spring 기반 [Petory](https://github.com/makkong1/Petory)와 함께 멀티스택 백엔드 포트폴리오를 구성합니다.

---

## 기술 스택

| 역할 | 기술 | 선택 이유 |
|------|------|-----------|
| 웹 프레임워크 | FastAPI | async 네이티브, 자동 Swagger 생성 |
| DB ORM | SQLAlchemy 2.0 (asyncpg) | async 쿼리, Mapped 타입 힌트 |
| DB | PostgreSQL 15 | pg_trgm 한국어 퍼지 검색 |
| 캐시 | Redis 7 | Sorted Set으로 트렌드 키워드 순위 관리 |
| 형태소 분석 | kiwipiepy | Java 불필요, pip 한 줄 설치 |
| 스케줄러 | APScheduler | max_instances=1로 중복 실행 방지 |
| HTTP 클라이언트 | httpx | async + 지수 백오프 재시도 |

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────┐
│  수집 파이프라인 (매일 자동 실행)                        │
│                                                     │
│  [행안부 공공API] ──► Collector ──► PostgreSQL        │
│       02:00                                         │
│                                                     │
│  [네이버 블로그API] ──► Collector ──► kiwipiepy        │
│       03:00               형태소 분석  ──► Redis       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  API 서빙                                            │
│                                                     │
│  Client ──► FastAPI ──► PostgreSQL  (시설/통계)       │
│                    └──► Redis       (트렌드)          │
└─────────────────────────────────────────────────────┘
```

---

## 핵심 기술 결정

### Keyset 페이지네이션
`LIMIT/OFFSET` 대신 `WHERE id > :cursor ORDER BY id LIMIT n` 방식 사용.  
OFFSET은 건너뛸 행을 매번 Full Scan하므로 O(n). Keyset은 인덱스만 탐색해 O(log n) 유지.

### pg_trgm 한국어 퍼지 검색
`LIKE '%검색어%'` 대신 GIN 인덱스 + `%` 유사도 연산자 사용.  
한국어 자모 단위 trigram을 인덱싱해 오타·부분 일치 검색을 지원.

### Redis Sorted Set 트렌드 캐싱
형태소 분석으로 추출한 키워드 빈도를 `ZADD`로 적재, `ZRANGE ... WITHSCORES` 로 상위 N개 조회.  
TTL 24시간으로 매일 갱신. Redis 미연결 시 503으로 graceful degradation.

### kiwipiepy 형태소 분석
KoNLPy 대신 kiwipiepy 선택. Java 런타임 불필요, `pip install` 만으로 동작.  
NNG(일반명사)·NNP(고유명사) 태그만 추출하고 불용어(추천, 후기 등) 필터링.

---

## API 명세

모든 엔드포인트는 `X-API-Key` 헤더 인증 필요.

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/facilities` | 시설 목록 (cursor 페이지네이션, 타입·지역 필터) | 일반 |
| GET | `/facilities/{id}` | 시설 상세 + 업종별 세부정보 | 일반 |
| GET | `/stats/summary` | 영업 중 시설 지역·타입별 통계 | 일반 |
| GET | `/trends/{category}` | 카테고리별 인기 키워드 Top N | 일반 |
| POST | `/collect/trigger` | 수동 수집 트리거 | 관리자 |

### 트렌드 카테고리

`snack` · `food` · `grooming` · `hospital` · `clothes`

### 응답 예시 — `GET /trends/snack?limit=5`

```json
{
  "category": "snack",
  "updated_at": "2026-04-21T03:05:00+00:00",
  "keywords": [
    { "keyword": "오리젠", "score": 42 },
    { "keyword": "로얄캐닌", "score": 38 },
    { "keyword": "퍼스트메이트", "score": 31 }
  ]
}
```

Swagger UI: `http://localhost:8000/docs`

---

## 실행 방법

### 사전 준비

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- [네이버 개발자센터](https://developers.naver.com) 블로그 검색 API 키

### 빠른 시작

```bash
# 1. 의존성 설치
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. DB 초기화
psql -U postgres -c "CREATE DATABASE petdata;"
psql -U postgres -d petdata -f migrations/init.sql

# 3. 환경변수 설정
cp .env.example .env  # 값 직접 입력

# 4. 서버 실행 (포트 8000)
uvicorn app.main:app --reload
```

### 테스트

```bash
pytest tests/ -v
```

---

## 환경변수

`.env` 파일에 설정 (`.env.example` 참고):

| 변수명 | 설명 |
|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/petdata` |
| `API_KEY_HASH` | 일반 API Key의 SHA-256 해시 |
| `ADMIN_API_KEY_HASH` | 관리자 API Key의 SHA-256 해시 |
| `PUBLIC_DATA_API_KEY` | 행안부 공공데이터 서비스키 |
| `HOSPITAL_API_KEY` | 동물병원 API 서비스키 |
| `NAVER_CLIENT_ID` | 네이버 검색 API Client ID |
| `NAVER_CLIENT_SECRET` | 네이버 검색 API Client Secret |
| `REDIS_URL` | Redis 연결 URL (기본: `redis://localhost:6379/0`) |

API Key 해시 생성:

```bash
python3 -c "import secrets,hashlib; k=secrets.token_hex(32); print('KEY:', k); print('HASH:', hashlib.sha256(k.encode()).hexdigest())"
```

---

## 프로젝트 구조

```
pet-data-api/
├── app/
│   ├── api/          # FastAPI 라우터
│   ├── analyzer/     # 형태소 분석 (kiwipiepy)
│   ├── cache/        # Redis 캐시 레이어
│   ├── collector/    # 공공데이터·네이버 수집기
│   ├── core/         # config, database, auth
│   ├── models/       # SQLAlchemy 모델
│   ├── scheduler/    # APScheduler 잡 설정
│   ├── schemas/      # Pydantic 응답 스키마
│   └── main.py
├── migrations/       # DB 초기화 SQL
└── tests/
```
