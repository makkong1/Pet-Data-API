import pytest
from datetime import datetime, timezone, timedelta
from app.ingestion.blog import _parse_freshness, _compute_scores


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y%m%d")


def test_parse_freshness_today():
    assert _parse_freshness(_days_ago(0)) == pytest.approx(1.0, abs=0.01)


def test_parse_freshness_90_days():
    assert _parse_freshness(_days_ago(90)) == pytest.approx(0.5, abs=0.02)


def test_parse_freshness_over_180_days():
    assert _parse_freshness(_days_ago(181)) == 0.0


def test_parse_freshness_none():
    assert _parse_freshness(None) == 0.0


def test_parse_freshness_invalid():
    assert _parse_freshness("invalid") == 0.0


def test_compute_scores_basic():
    aggregator = {
        "해피독": {"count": 5, "freshness_sum": 4.0},
        "멍멍샵": {"count": 3, "freshness_sum": 2.4},
    }
    result = _compute_scores(aggregator)
    assert len(result) == 2
    assert result[0]["name"] == "해피독"
    assert result[0]["score"] == pytest.approx(1.0)
    assert 0.0 < result[1]["score"] <= 1.0
    assert all(0.0 <= r["score"] <= 1.0 for r in result)


def test_compute_scores_min_mention_filter():
    aggregator = {
        "해피독": {"count": 5, "freshness_sum": 4.0},
        "노이즈": {"count": 1, "freshness_sum": 0.8},
    }
    result = _compute_scores(aggregator)
    names = [r["name"] for r in result]
    assert "해피독" in names
    assert "노이즈" not in names


def test_compute_scores_all_stale_returns_empty():
    aggregator = {
        "해피독": {"count": 5, "freshness_sum": 0.0},
        "멍멍샵": {"count": 3, "freshness_sum": 0.0},
    }
    assert _compute_scores(aggregator) == []


def test_compute_scores_empty():
    assert _compute_scores({}) == []


def test_compute_scores_top20_limit():
    aggregator = {
        f"미용실{i}": {"count": i + 2, "freshness_sum": float(i + 2)}
        for i in range(30)
    }
    result = _compute_scores(aggregator)
    assert len(result) == 20


def test_compute_scores_result_fields():
    aggregator = {"해피독": {"count": 4, "freshness_sum": 3.2}}
    result = _compute_scores(aggregator)
    assert len(result) == 1
    r = result[0]
    assert r["name"] == "해피독"
    assert r["mention_count"] == 4
    assert r["avg_freshness"] == pytest.approx(0.8, abs=0.001)
    assert r["score"] == pytest.approx(1.0)
