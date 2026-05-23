import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_extract_popular_names_cross_query_link_dedupe():
    """동일 link가 여러 쿼리에서 반환되어도 mention_count는 1."""
    dup_post = {
        "title": "해피독 미용실 후기",
        "description": "해피독미용실 방문기",
        "link": "https://blog.naver.com/unique",
        "postdate": "20260501",
    }

    async def fake_search(query, display=100, sort="sim"):
        return [dup_post]

    with patch("app.ingestion.blog.search_naver_blog", side_effect=fake_search):
        from app.ingestion.blog import extract_popular_names
        result = await extract_popular_names("grooming")

    # grooming has 3 queries — same link returned 3 times but deduplicated to 1
    해피독_entries = [r for r in result if r["name"] == "해피독"]
    if 해피독_entries:
        assert 해피독_entries[0]["mention_count"] == 1


@pytest.mark.asyncio
async def test_extract_popular_names_unknown_context_returns_empty():
    with patch("app.ingestion.blog.search_naver_blog", new=AsyncMock(return_value=[])):
        from app.ingestion.blog import extract_popular_names
        result = await extract_popular_names("unknown_xyz")
    assert result == []


@pytest.mark.asyncio
async def test_save_popular_skips_empty():
    with patch("app.ingestion.blog.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        from app.ingestion.blog import save_popular
        await save_popular("grooming", [])
    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_save_popular_writes_json():
    import json
    results = [{"name": "해피독", "mention_count": 5, "avg_freshness": 0.8, "score": 1.0}]
    with patch("app.ingestion.blog.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        from app.ingestion.blog import save_popular, POPULAR_TTL
        await save_popular("grooming", results)
    mock_redis.setex.assert_called_once()
    key, ttl, payload = mock_redis.setex.call_args.args
    assert key == "popular:grooming"
    assert ttl == POPULAR_TTL
    assert json.loads(payload) == results


@pytest.mark.asyncio
async def test_collect_popular_for_context_aliases_supplies():
    """snack → supplies로 정규화된 쿼리셋을 사용."""
    called_queries: list = []

    async def fake_search(query, display=100, sort="sim"):
        called_queries.append(query)
        return []

    with patch("app.ingestion.blog.search_naver_blog", side_effect=fake_search):
        from app.ingestion.blog import collect_popular_for_context
        await collect_popular_for_context("snack")

    # snack → supplies → 8 queries (supplies2+snack2+food2+clothes2)
    assert len(called_queries) == 8
