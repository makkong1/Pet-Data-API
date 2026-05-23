# pet-data-api — 프로젝트 개요

## 한 줄 설명

**네이버 블로그 검색**으로 반려동물 관련 **트렌드 키워드**와 **업종·컨텍스트별 인기 상호**를 주기적으로 수집하여 **Redis**에 두고, **REST API**로 조회 가능하게 하는 **Python/FastAPI** 서비스입니다.

PostgreSQL 행안부 공공 시설 적재·지오코딩·추천 엔진·이벤트 환류 등은 **이 레포 현재 버전의 범위에 포함되지 않습니다.**

## 무엇을 제공하는가

| 구분 | 내용 |
|------|------|
| 트렌드 | 카테고리별 키워드 빈도(형태소 분석 포함). **`GET /trends/{category}`** |
| 인기 상호(Popularity) | 컨텍스트별 상호 이름·언급·신선도 등 점수. **`GET /popular/{context}`** |
| 수동 배치 | 관리자 키로 트렌드/인기 수집 즉시 큐잉. **`POST /collect/trigger`** (`JSON` 바디 필수) |

## 데이터 저장

- **Redis만** 사용. 앱 시작 시 Postgres 마이그레이션은 불필요합니다.
- `migrations/` 이 있다면 과거 레거시용 DDL 로만 취급합니다.

## 스케줄

- 매일 로컬 **18:00** — 트렌드 배치  
- 매일 로컬 **18:10** — 인기(Popularity) 배치  

`app/platform/scheduler/jobs.py` 참고.

## 연관 문서

- 흐름도: [`docs/분석/DATA-AND-API-FLOW.md`](분석/DATA-AND-API-FLOW.md)
- 아키텍처: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
- 실행·예시: [`docs/USAGE.md`](USAGE.md)
- Petory 쪽 클라이언트 가이드: [`docs/PETORY-INTEGRATION.md`](PETORY-INTEGRATION.md)
- 설계 근거(SSOT): [`docs/superpowers/specs/2026-05-23-popularity-intelligence-redesign.md`](superpowers/specs/2026-05-23-popularity-intelligence-redesign.md)
