# pet-data-api — 변경 타임라인

이 파일은 과거 브랜치(v2·v3)와 최신 상태를 한곳에서 보기 위해 유지합니다. **현재 동작 SSOT 는 루트 `README.md` 와 [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md) 입니다.**

---

## 현재 — 2026-05-23 Popularity Intelligence

**목표**: 추천·Postgres 의존도 제거하고, 네이버 블로그 기반 **트렌드** + **인기 상호**만 Redis 에 적재 후 API 제공.

### 엔드포인트

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| GET | `/healthz` | 없음 | Liveness |
| GET | `/readyz` | 없음 | **Redis** ping 만 |
| GET | `/metrics` | 없음 | Prometheus 가능 시 |
| GET | `/trends/{category}` | `X-API-Key` | Redis Sorted Set 순위 조회 |
| GET | `/popular/{context}` | `X-API-Key` | Redis JSON 배열 조회 |
| POST | `/collect/trigger` | 관리자 `X-API-Key` | `{"targets":["trends"|"popular",...]}` (JSON 필수, Breaking) |

### 스케줄 (로컬 시각)

- 18:00 — `run_trend_collection`
- 18:10 — `run_popular_collection`

### 문서 폐기

- `docs/GROOMING-RECOMMEND-MVP.md` — 삭제(그루밍 MVP·추천 파이프 문서 더 이상 유효하지 않음)
- `docs/INGESTION-VS-SERVING.md` — 삭제(`ingestion/` vs `serving/` 매핑은 [`ARCHITECTURE.md`](ARCHITECTURE.md)·[`분석/DATA-AND-API-FLOW.md`](분석/DATA-AND-API-FLOW.md) 로 대체)

배포·클라이언트 검증 명령은 [`USAGE.md`](USAGE.md).

---

## 아카이브 — 2026-05-13 v3 스냅샷 요약

> 아래 기능은 **당시 계획/구현되어 있던 pet-data-api v3 브랜치** 에 대한 요약입니다. **현 코드베이스에서는 제거**되었으며, 레포에는 설명 목적으로만 남깁니다.

- **목표 표현**: “외부 데이터 어댑터 + 가벼운 룰 기반 추천” 과 엔드포인트 책임 분리
- **대표적인 제거 요소**: `POST /recommend`(빠른 랭킹 + 규칙 카피), `POST /recommend/copy`(LLM), `GET /facilities/search`, `GET /trends/.../timeseries`(Postgres), `POST /events/recommendation`, Postgres 마이그레이션·랭커·시설 검색 코드 경로 등
- **관측성**: v3 초안에서는 `/readyz` 가 DB + Redis 검사였으나 **현재는 Redis만** 검사

---

## 아카이브 — v2 및 그 이전

단일 서비스에 시설 Postgres 적재·트렌드·추천·(선택) LLM 이 혼합되던 초기 형태였습니다.  
세부 회고는 Git 히스토리와 `docs/superpowers/` 아래 과거 플랜을 참고하세요.
