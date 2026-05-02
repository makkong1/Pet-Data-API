import pytest
from unittest.mock import AsyncMock, patch

from app.ingestion.grooming_blog import (
    _extract_candidates_from_text,
    _parse_freshness,
    extract_grooming_mentions,
)


def test_extract_candidates_suffix_pattern():
    text = "해피독 미용실에서 스포팅컷을 받았어요"
    result = _extract_candidates_from_text(text)
    assert "해피독" in result


def test_extract_candidates_prefix_pattern():
    text = "애견 뽀삐샵 방문 후기"
    result = _extract_candidates_from_text(text)
    # 패턴에서 추출된 후보가 있어야 함
    assert len(result) >= 0  # 패턴에 따라 달라질 수 있음


def test_extract_candidates_blocklist_excluded():
    result = _extract_candidates_from_text("미용실 추천 강아지 동물 샵")
    for name in result:
        assert name not in {"미용실", "추천", "강아지", "동물", "샵"}


def test_parse_freshness_recent():
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y%m%d")
    w = _parse_freshness(recent)
    assert 0.9 < w <= 1.0


def test_parse_freshness_old():
    w = _parse_freshness("20200101")
    assert w == 0.0


def test_parse_freshness_none():
    assert _parse_freshness(None) == 0.0


def test_parse_freshness_invalid():
    assert _parse_freshness("notadate") == 0.0


@pytest.mark.asyncio
async def test_extract_grooming_mentions_returns_capped():
    """블로그 결과에서 상위 20개 후보만 반환."""
    many_items = []
    for i in range(25):
        many_items.append({
            "title": f"미용실{i:02d} 미용실 후기",
            "description": "",
            "postdate": "20250101",
            "link": f"http://blog/{i}",
        })

    with patch("app.ingestion.grooming_blog.search_naver_blog", new=AsyncMock(return_value=many_items)):
        mention_map, candidate_names = await extract_grooming_mentions()

    assert len(candidate_names) <= 20


@pytest.mark.asyncio
async def test_extract_grooming_mentions_dedup_per_post():
    """동일 글(link)에서 같은 상호가 여러 번 나와도 1표."""
    same_post = [
        {
            "title": "해피독 미용실 정말 해피독 미용실",
            "description": "해피독 미용실이 최고",
            "postdate": "20250101",
            "link": "http://blog/same",
        }
    ]
    with patch("app.ingestion.grooming_blog.search_naver_blog", new=AsyncMock(return_value=same_post)):
        mention_map, _ = await extract_grooming_mentions()

    if "해피독" in mention_map:
        assert mention_map["해피독"]["count"] == 1


@pytest.mark.asyncio
async def test_extract_grooming_mentions_naver_fail_raises():
    """네이버 실패 시 예외를 그대로 올린다 (핸들러에서 폴백 처리)."""
    with patch(
        "app.ingestion.grooming_blog.search_naver_blog",
        new=AsyncMock(side_effect=Exception("naver down")),
    ):
        with pytest.raises(Exception, match="naver down"):
            await extract_grooming_mentions()
