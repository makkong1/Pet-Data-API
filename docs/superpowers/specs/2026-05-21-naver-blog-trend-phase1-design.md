# 스펙: 네이버 블로그 트렌드 수집 Phase 1

상태: **승인(Approved)**
범위: `app/ingestion/naver.py` Phase 1 (dual-sort + dedup + 필드 정규화)
Phase 2 (intent / BlogTrendRawItem): 별도 사이클

---

## 배경

현재 `search_naver_blog`는 `sort=sim` 단일 호출, `collect_category_trends`는 중복 제거 없이 단순 extend. 같은 링크가 여러 쿼리·sort에서 반복 집계되며, 최신 트렌드(`date`) 신호가 완전히 누락된다.

---

## 목표 (Phase 1)

| # | 목표 |
|---|------|
| 1 | `date` + `sim` 두 sort 결과를 모두 반영한다 |
| 2 | 동일 `link` 는 한 번만 집계 재료로 쓴다 |
| 3 | 네이버 API가 제공하는 `bloggername`/`bloggerlink` 필드를 보존한다 |
| 4 | 호출 수 증가를 asyncio.gather + 세마포어로 레이턴시 상쇄·안전 제한한다 |

---

## 변경 파일

`app/ingestion/naver.py` 만 수정. runner·trend analyzer 계약 변경 없음.

---

## 설계

### `search_naver_blog` — sort 파라미터 추가

```python
async def search_naver_blog(query: str, display: int = 100, sort: str = "sim") -> list[dict]:
    params = {"query": query, "display": display, "sort": sort}
    ...
    return [
        {
            "title":        _strip_html(i.get("title", "")),
            "description":  _strip_html(i.get("description", "")),
            "link":         i.get("link", ""),
            "postdate":     i.get("postdate", ""),
            "blogger_name": i.get("bloggername", ""),
            "blogger_link": i.get("bloggerlink", ""),
        }
        for i in items
    ]
```

- 기본값 `sort="sim"` 유지 → 기존 호출부 무변경
- `blogger_name` / `blogger_link`: 현재 drop 중인 필드 보존 (Phase 2 Raw 모델 계약 준비)

### `collect_category_trends` — gather + 동적 세마포어 + link dedup

```python
async def collect_category_trends(category: str) -> list[dict]:
    queries = CATEGORY_KEYWORDS.get(category, [])
    sem_limit = max(1, min(8, len(queries) * 2))
    semaphore = asyncio.Semaphore(sem_limit)

    async def _fetch(q: str, sort: str) -> list[dict]:
        async with semaphore:
            return await search_naver_blog(q, sort=sort)

    tasks = [_fetch(q, sort) for q in queries for sort in ("sim", "date")]
    batches = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[str] = set()
    results: list[dict] = []
    for batch in batches:
        if isinstance(batch, Exception):
            logger.warning("naver blog fetch failed [%s]: %s", category, batch)
            continue
        for item in batch:
            link = item.get("link", "")
            if link and link not in seen:
                seen.add(link)
                results.append(item)
    return results
```

**세마포어 동적 계산 근거**

| 카테고리 | 쿼리 수 | tasks | sem_limit |
|----------|---------|-------|-----------|
| supplies | 2 | 4 | 4 |
| grooming | 3 | 6 | 6 |
| cafe | 3 | 6 | 6 |
| hotel | 3 | 6 | 6 |
| 상한 클램프 | — | — | 8 (질의 확장 이후에도 안전) |

- 예외 발생 시 `logging.warning`으로 카테고리와 오류 기록, 다른 batch는 계속 진행

---

## 영향 범위

| 구간 | 조치 |
|------|------|
| `runner.run_trend_collection` | 변경 없음. `collect_category_trends` 반환 타입 `list[dict]` 유지 |
| `aggregate_keywords` | 변경 없음. `title`+`description` 키 유지 |
| Redis / Postgres 시계열 | 변경 없음. 집계 결과(`dict[str,int]`) 계약 유지 |
| 일일 API 호출량 | 현재 ~29 → ~58. 25,000 한도 대비 안전 |

---

## 검증 기준

- [ ] 카테고리별로 `sim` / `date` 결과가 각각 로그에 찍히는 단위 테스트 통과
- [ ] 동일 `link`가 결과 list에 중복 없음을 검증하는 단위 테스트 통과
- [ ] `blogger_name` / `blogger_link` 필드가 결과 dict에 포함
- [ ] 개별 호출 실패 시 warning 로그 출력 후 나머지 결과 정상 반환
- [ ] `runner.run_trend_collection` dry-run 후 Redis 키 스키마 깨지지 않음

---

## 범위 외 (Phase 2)

- `intent` 메타데이터, `BlogTrendRawItem` 타입 계약
- `quality_score` / 광고 노이즈 필터
- `CATEGORY_KEYWORDS` 질의 확장 (6순위)
