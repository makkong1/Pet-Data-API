# Step 2: 네이버 카페 API 어댑터 추가

## 목표

`app/ingestion/naver.py`에 `search_naver_cafe()` 함수를 추가하고,
블로그·카페 각각을 `PostRecord`로 변환하는 어댑터 함수 두 개를 추가한다.
기존 `search_naver_blog()` 시그니처와 반환값은 **변경하지 않는다**.

## 배경

네이버 카페 검색 API (`/v1/search/cafearticle.json`):
- 동일한 `X-Naver-Client-Id` / `X-Naver-Client-Secret` 사용 (별도 신청 불필요)
- 파라미터: `query`, `display`(10-100), `start`(1-1000), `sort`(`sim`|`date`) — 블로그와 동일
- 응답 핵심 필드: `title`, `description`, `link`, `postdate` — 블로그와 동일
- 블로그와 다른 점: `bloggername`/`bloggerlink` 대신 `cafename`/`cafeurl` 반환

## 변경 파일

### `app/ingestion/naver.py` (수정)

#### 추가 1 — 카페 검색 URL 상수

기존 `NAVER_BLOG_URL` 바로 아래에 추가:

```python
NAVER_CAFE_URL = "https://openapi.naver.com/v1/search/cafearticle.json"
```

#### 추가 2 — `search_naver_cafe()` 함수

`search_naver_blog()` 함수 바로 아래에 추가:

```python
async def search_naver_cafe(query: str, display: int = 100, sort: str = "sim") -> list[dict]:
    """네이버 카페 검색 API 호출. 반환 필드를 블로그와 같은 키로 정규화한다."""
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": sort}
    timeout = settings.NAVER_TIMEOUT_MS // 1000

    data = await _fetch_naver(NAVER_CAFE_URL, params=params, headers=headers, timeout=timeout)
    items = data.get("items", [])
    _log.info(
        "naver_cafe search_ok query_preview=%r display=%s sort=%s items=%s",
        _preview_text(query, 100), display, sort, len(items),
    )
    return [
        {
            "title":        _strip_html(i.get("title", "")),
            "description":  _strip_html(i.get("description", "")),
            "link":         i.get("link", ""),
            "postdate":     i.get("postdate", ""),
            "cafe_name":    _strip_html(i.get("cafename", "")),   # 카페 전용 필드
            "cafe_link":    i.get("cafeurl", ""),
        }
        for i in items
    ]
```

#### 추가 3 — PostRecord 어댑터 함수 두 개

파일 맨 아래에 추가 (import는 함수 내부 지연 import로 순환 방지):

```python
def _blog_items_to_records(items: list[dict]) -> list:
    """search_naver_blog() 결과 → list[PostRecord]"""
    from app.ingestion.record import PostRecord
    return [
        PostRecord(
            title=i["title"],
            description=i["description"],
            link=i["link"],
            postdate=i["postdate"],
            source="naver_blog",
            author_name=i.get("blogger_name", ""),
            author_link=i.get("blogger_link", ""),
        )
        for i in items
        if i.get("link")
    ]


def _cafe_items_to_records(items: list[dict]) -> list:
    """search_naver_cafe() 결과 → list[PostRecord]"""
    from app.ingestion.record import PostRecord
    return [
        PostRecord(
            title=i["title"],
            description=i["description"],
            link=i["link"],
            postdate=i["postdate"],
            source="naver_cafe",
            author_name=i.get("cafe_name", ""),
            author_link=i.get("cafe_link", ""),
        )
        for i in items
        if i.get("link")
    ]
```

## AC (Acceptance Criteria)

```bash
cd /Users/maknkkong/project/pet-data-api && source venv/bin/activate

# 1. import 확인
python -c "
from app.ingestion.naver import (
    search_naver_cafe, NAVER_CAFE_URL,
    _blog_items_to_records, _cafe_items_to_records,
)
print('imports ok')
print('cafe url:', NAVER_CAFE_URL)
"

# 2. 어댑터 변환 확인 (API 호출 없이)
python -c "
from app.ingestion.naver import _blog_items_to_records, _cafe_items_to_records

blog_raw = [{'title': '블로그글', 'description': '내용', 'link': 'http://blog/1',
             'postdate': '20250524', 'blogger_name': '블로거', 'blogger_link': 'http://b'}]
cafe_raw = [{'title': '카페글', 'description': '내용', 'link': 'http://cafe/1',
             'postdate': '20250524', 'cafe_name': '강아지카페', 'cafe_link': 'http://c'}]

br = _blog_items_to_records(blog_raw)
cr = _cafe_items_to_records(cafe_raw)

assert br[0].source == 'naver_blog'
assert br[0].author_name == '블로거'
assert cr[0].source == 'naver_cafe'
assert cr[0].author_name == '강아지카페'

# to_dict() 호환 확인
d = br[0].to_dict()
assert 'blogger_name' in d
print('adapter ok', br[0].source, cr[0].source)
"

# 3. 기존 테스트 통과
PYTHONPATH=. pytest tests/ -v
```
