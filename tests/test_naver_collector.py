import logging
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
    # 쿼리마다 고유 link로 dedup 통과, AsyncMock으로 gather 호환
    async def fake_search(query, display=100, sort="sim"):
        return [{
            "title": "t", "description": "d",
            "link": f"https://blog.naver.com/{query}-{sort}",
            "postdate": "", "blogger_name": "", "blogger_link": "",
        }]

    with patch("app.ingestion.naver.search_naver_blog", side_effect=fake_search):
        result = await collect_category_trends("snack")

    queries = CATEGORY_KEYWORDS["snack"]
    assert len(result) == len(queries) * 2  # sim + date 각각 1개씩


@pytest.mark.asyncio
async def test_collect_category_trends_calls_both_sorts():
    called_sorts: list[str] = []

    async def fake_search(query, display=100, sort="sim"):
        called_sorts.append(sort)
        return [{
            "title": "t", "description": "d",
            "link": f"https://blog.naver.com/{query}-{sort}",
            "postdate": "", "blogger_name": "", "blogger_link": "",
        }]

    with patch("app.ingestion.naver.search_naver_blog", side_effect=fake_search):
        await collect_category_trends("snack")

    assert "sim" in called_sorts
    assert "date" in called_sorts


@pytest.mark.asyncio
async def test_collect_category_trends_deduplicates_by_link():
    dup_item = {
        "title": "t", "description": "d",
        "link": "https://blog.naver.com/same",
        "postdate": "", "blogger_name": "", "blogger_link": "",
    }

    with patch("app.ingestion.naver.search_naver_blog", new=AsyncMock(return_value=[dup_item])):
        result = await collect_category_trends("snack")

    # 동일 link는 1번만 남음
    assert len(result) == 1
    assert result[0]["link"] == "https://blog.naver.com/same"


@pytest.mark.asyncio
async def test_collect_category_trends_logs_warning_on_fetch_error(caplog):
    async def failing_search(query, display=100, sort="sim"):
        raise RuntimeError("network error")

    with patch("app.ingestion.naver.search_naver_blog", side_effect=failing_search):
        with caplog.at_level(logging.WARNING, logger="app.ingestion.naver"):
            result = await collect_category_trends("snack")

    assert result == []
    assert any("naver blog fetch failed" in r.message for r in caplog.records)


def test_category_keywords_has_required_categories():
    required = {"supplies", "snack", "food", "grooming", "hospital", "clothes"}
    assert required.issubset(set(CATEGORY_KEYWORDS.keys()))


@pytest.mark.asyncio
async def test_search_naver_blog_passes_sort_to_params():
    mock_response = {"items": []}
    with patch("app.ingestion.naver.fetch_public_api", new=AsyncMock(return_value=mock_response)) as mock_fetch:
        await search_naver_blog("강아지 간식", sort="date")
    assert mock_fetch.call_args.kwargs["params"]["sort"] == "date"


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
