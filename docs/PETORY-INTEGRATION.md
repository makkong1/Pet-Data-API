## Petory ↔ pet-data-api 연동 가이드

> 대상: Petory(Java/Spring) 백엔드 또는 프론트에서 트렌드·인기 데이터를 불러 오는 경우  
> 현재 pet-data-api: **PostgreSQL 시설 데이터·추천(`/recommend`)·이벤트 콜백 없음** — **Redis 에 캐시된 트렌드와 인기 상호만** 제공합니다.

짝 문서: [`V3-CHANGES.md`](V3-CHANGES.md) (변경 타임라인), [`USAGE.md`](USAGE.md) (curl·환경 변수).

특히 이전 버전 문서나 클라이언트가 의존하던 다음 항목은 **제거·폐기**되었습니다.

- `POST /recommend`, `POST /recommend/copy`
- `GET /facilities*`, `GET /stats/summary`
- `POST /events/recommendation`
- `GET /trends/{category}/timeseries`(Postgres 시계열)
- 카카오 지오코딩·Ollama·그루밍 MVP 플래그

---

### 1. 한 줄 요약

| 기능 | 방법 |
|------|------|
| 카테고리 트렌드 키워드 | `GET /trends/{category}` + `X-API-Key` |
| 업종별 인기 상호 | `GET /popular/{context}` + `X-API-Key` |
| 헬스 | `GET /healthz`(liveness), `GET /readyz`(Redis) |

카테고리·컨텍스트 목록 및 별칭은 [`USAGE.md`](USAGE.md) 참고 (`snack`/`food`/`clothes` → 인기만 `supplies` 로 귀결).

---

### 2. Petory 에서 할 일

1. **설정**: pet-data-api Base URL 과 **일반** API 평문 키를 안전하게 주입합니다. 헤더는 항상 `X-API-Key`.
2. **추적**: 선택적으로 `X-Request-Id` 를 보냅니다. pet-data-api 는 동일 값을 응답 헤더에 에코합니다(로깅 상관 분석용).
3. **호출 패턴**: UI 는 **캐시된 Redis 데이터만** 받습니다. “실시간 최신 블로그 원문”이 아니라 **마지막 배치**(스켈줄 18:00/18:10 또는 운영자 트리거) 결과입니다.
4. **데이터 부재 처리**: 트렌드/인기 키가 비어 있으면 서비스는 **503** 과 짧은 `detail` 을 줄 수 있습니다. Petory 에서는 카드 숨김·재시도·기본 카피로 처리합니다.

---

### 3. 예시 페이로드

**`GET /trends/{category}`** (요약 형태):

```json
{
  "category": "grooming",
  "updated_at": "2026-05-22T09:05:01.234567+00:00",
  "keywords": [
    {"keyword": "스포팅컷", "score": 41}
  ]
}
```

**`GET /popular/{context}`** 항목(`PopularEntry`, 최대 반환 길이 쿼리로 제한):

```json
[
  {
    "name": "해피펫 미용실",
    "mention_count": 12,
    "avg_freshness": 0.85,
    "score": 0.91
  }
]
```

점수 계산 규칙은 수집기(`runner`·파서) 구현을 따르고, API 계약만 위 필드를 보장합니다.

---

### 4. 운영자 수동 수집 (선택)

Petory 가 아니라 **백오피스/파이프라인** 에서 호출합니다. 헤더 `X-API-Key` 는 **관리자** 키여야 하며 바디가 없으면 안 됩니다.

```http
POST /collect/trigger
Content-Type: application/json

{"targets": ["trends", "popular"]}
```

---

### 5. 설계 근거

상세 명세 및 마이그레이션 노트는 [`superpowers/specs/2026-05-23-popularity-intelligence-redesign.md`](superpowers/specs/2026-05-23-popularity-intelligence-redesign.md) 입니다.
