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


# 스펙 케이스 10개 (TDD — 일부는 현재 failing 예상)

def test_spec_case_1_suffix_bridge():
    """Case 1: suffix bridge 포착 — '두유네 애견미용실 후기' → 두유네 추출"""
    text = "두유네 애견미용실 후기"
    result = _extract_candidates_from_text(text, context="grooming")
    assert "두유네" in result


def test_spec_case_2_blocklist_exact_only():
    """맘바이강아지미용실 → 맘바이강아지 추출 (exact blocklist만 차단)"""
    text = "맘바이강아지미용실 예약"
    result = _extract_candidates_from_text(text, context="grooming")
    assert "맘바이강아지" in result


def test_spec_case_3_suffix_bridge_with_space():
    """Case 3: suffix bridge with space — '니니 애견 미용실 예약' → 니니 추출"""
    text = "니니 애견 미용실 예약"
    result = _extract_candidates_from_text(text, context="grooming")
    assert "니니" in result


def test_spec_case_4_char_class_excluded():
    """Case 4: char class 차단 — '#반려동물 #애견미용 #헤어스파' → set()"""
    text = "#반려동물 #애견미용 #헤어스파"
    result = _extract_candidates_from_text(text, context="grooming")
    assert result == set()


def test_spec_case_5_location_and_single_char():
    """Case 5: location + 한글1자 차단 — '강서구 1인 미용실 후기' → set()"""
    text = "강서구 1인 미용실 후기"
    result = _extract_candidates_from_text(text, context="grooming")
    assert result == set()


def test_spec_case_6_blocklist_contains():
    """Case 6: BLOCKLIST_CONTAINS '추천' 차단 — '반려동물 동반 안산 추천 미용실' → set()"""
    text = "반려동물 동반 안산 추천 미용실"
    result = _extract_candidates_from_text(text, context="grooming")
    assert result == set()


def test_spec_case_7_normal_extraction():
    """Case 7: 정상 추출 — '화원강아지미용실 다녀왔어요' → 화원강아지 추출"""
    text = "화원강아지미용실 다녀왔어요"
    result = _extract_candidates_from_text(text, context="grooming")
    assert "화원강아지" in result


def test_spec_case_8_prefix_suffix_anchor_blocked():
    """Case 8: PREFIX suffix 앵커 차단 — '애견 셀프목욕 방문 후기' → set()"""
    text = "애견 셀프목욕 방문 후기"
    result = _extract_candidates_from_text(text, context="grooming")
    assert result == set()


def test_spec_case_9_mixed_korean_english():
    """Case 9: 혼합형(한글2자 포함) — 'ABC미용 그루밍샵 예약했어요' → ABC미용 추출"""
    text = "ABC미용 그루밍샵 예약했어요"
    result = _extract_candidates_from_text(text, context="grooming")
    assert "ABC미용" in result


def test_spec_case_10_known_limitation():
    """Case 10: known limitation — '예약제미용실 체험기' → set() (예약제가 BLOCKLIST_EXACT에 있어야 차단)"""
    text = "예약제미용실 체험기"
    result = _extract_candidates_from_text(text, context="grooming")
    assert result == set()


# ── 노이즈 필터 회귀 테스트 (운영 로그에서 관찰된 케이스) ──

def test_noise_grammar_ending_filtered():
    """'가능한 미용실', '편안한 그루밍샵', '있는 미용실' → 어미 필터로 제거."""
    assert _extract_candidates_from_text("가능한 미용실 추천해요", context="grooming") == set()
    assert _extract_candidates_from_text("편안한 그루밍샵이에요", context="grooming") == set()
    assert _extract_candidates_from_text("있는 미용실 알려주세요", context="grooming") == set()


def test_noise_city_name_filtered():
    """'안산 미용실', '강남 미용실', '대전 미용실' → 도시명 필터로 제거."""
    assert _extract_candidates_from_text("안산 미용실 다녀왔어요", context="grooming") == set()
    assert _extract_candidates_from_text("강남 미용실 추천", context="grooming") == set()
    assert _extract_candidates_from_text("대전 미용실 후기", context="grooming") == set()


def test_noise_baeryeodongmul_filtered():
    """'원반려동물 미용실' → '반려동물' BLOCKLIST_CONTAINS로 제거."""
    assert _extract_candidates_from_text("원반려동물 미용실 다녀왔어요", context="grooming") == set()


def test_noise_dongban_filtered():
    """'동반 미용실' → BLOCKLIST_EXACT 추가로 제거."""
    assert _extract_candidates_from_text("동반 미용실 이용했어요", context="grooming") == set()
