import pytest
from unittest.mock import AsyncMock, patch
from app.ingestion.naver import search_naver_blog, collect_category_trends, CATEGORY_KEYWORDS


@pytest.mark.asyncio
async def test_search_naver_blog_returns_items():
    mock_response = {
        "items": [
            {"title": "강아지 <b>간식</b> 추천 TOP5", "description": "오리젠 로얄캐닌 후기"},
            {"title": "고양이 간식 후기", "description": "퍼스트메이트 정보"},
        ]
    }
    with patch("app.ingestion.naver.fetch_public_api", new=AsyncMock(return_value=mock_response)):
        items = await search_naver_blog("강아지 간식 추천")

    assert len(items) == 2
    assert items[0]["title"] == "강아지 간식 추천 TOP5"


@pytest.mark.asyncio
async def test_collect_category_trends_merges_queries():
    mock_items = [{"title": "test", "description": "desc"}]
    with patch("app.ingestion.naver.search_naver_blog", return_value=mock_items):
        result = await collect_category_trends("snack")

    queries = CATEGORY_KEYWORDS["snack"]
    assert len(result) == len(queries) * len(mock_items)


def test_category_keywords_has_required_categories():
    required = {"supplies", "snack", "food", "grooming", "hospital", "clothes"}
    assert required.issubset(set(CATEGORY_KEYWORDS.keys()))


@pytest.mark.asyncio
async def test_search_naver_blog_passes_sort_to_params():
    mock_response = {"items": []}
    with patch("app.ingestion.naver.fetch_public_api", new=AsyncMock(return_value=mock_response)) as mock_fetch:
        await search_naver_blog("강아지 간식", sort="date")
    _, kwargs = mock_fetch.call_args
    assert kwargs["params"]["sort"] == "date"


@pytest.mark.asyncio
async def test_search_naver_blog_includes_blogger_fields():
    mock_response = {
        "items": [
            {
                "title": "강아지 <b>간식</b>",
                "description": "설명",
                "link": "https://blog.naver.com/post/1",
                "postdate": "20240101",
                "bloggername": "펫블로거",
                "bloggerlink": "https://blog.naver.com/petblog",
            }
        ]
    }
    with patch("app.ingestion.naver.fetch_public_api", new=AsyncMock(return_value=mock_response)):
        items = await search_naver_blog("강아지 간식")

    assert items[0]["blogger_name"] == "펫블로거"
    assert items[0]["blogger_link"] == "https://blog.naver.com/petblog"
