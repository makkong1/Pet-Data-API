import pytest
from unittest.mock import AsyncMock, patch

from app.ingestion.grooming_blog import _extract_candidates_from_text, extract_grooming_mentions


def test_extract_candidates_rejects_non_grooming_text():
    text = "세월호 기억공간 기억과빛 사적인공간 오늘온"
    assert _extract_candidates_from_text(text) == set()


def test_extract_candidates_uses_pattern_not_plain_nouns():
    text = "오늘온 애견미용 후기"
    names = _extract_candidates_from_text(text)
    assert "오늘온" in names
    assert "후기" not in names
    assert "애견미용" not in names


@pytest.mark.asyncio
async def test_extract_grooming_mentions_applies_min_mention_count():
    query1_items = [
        {"title": "멍멍샵 애견미용 후기", "description": "친절함", "link": "post-1", "postdate": "20260501"},
        {"title": "오늘온 애견미용 후기", "description": "괜찮음", "link": "post-2", "postdate": "20260501"},
    ]
    query2_items = [
        {"title": "멍멍샵 애견미용 추천", "description": "재방문", "link": "post-3", "postdate": "20260430"},
    ]

    with patch("app.ingestion.grooming_blog.search_naver_blog", new=AsyncMock(side_effect=[query1_items, query2_items])):
        mention_map, candidate_names = await extract_grooming_mentions(req_id="test")

    assert "멍멍샵" in mention_map
    assert mention_map["멍멍샵"]["count"] == 2
    assert "오늘온" not in mention_map
    assert candidate_names == ["멍멍샵"]
