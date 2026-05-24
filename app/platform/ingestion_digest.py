"""배치 수집(네이버 → 집계 → Redis 적재) 시점 요약 로그.

API 요청별 `integration_trace`/access 로그와 달리, **스케줄/collect-trigger** 에서 무엇이 쌓였는지
grep 용으로 남긴다. 검색 예: `grep ingestion-digest` 또는 로거명 `pet_data_api.ingestion_digest`.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Sequence

_LOG = logging.getLogger("pet_data_api.ingestion_digest")


def redis_popular_key_slug(runner_context: str) -> str:
    c = runner_context.strip().lower() if runner_context else "supplies"
    if c in ("snack", "food", "clothes"):
        return "supplies"
    return c


def _truncate(s: str, n: int) -> str:
    s = str(s).replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")


def log_trend_stored(
    category: str,
    *,
    blog_items: int,
    term_count: int,
    counts: Counter | dict[str, int],
    preview_n: int = 8,
) -> None:
    """Redis ZSET trends:{category}:keywords 에 반영된 뒤 요약."""
    c = counts if isinstance(counts, Counter) else Counter(counts)
    mc = c.most_common(min(preview_n, max(1, len(c))))
    preview = [{k: v} for k, v in mc]
    _LOG.info(
        "[ingestion-digest] trend_stored category=%r blog_posts=%d redis=zset:trends:%s:keywords "
        "+ meta:trends:%s:updated_at terms=%d preview_top=%s",
        category,
        blog_items,
        category,
        category,
        term_count,
        preview,
    )


def log_trend_skipped(category: str, *, blog_items: int, reason: str) -> None:
    _LOG.warning(
        "[ingestion-digest] trend_skip category=%r blog_posts=%d reason=%s",
        category,
        blog_items,
        reason,
    )


def log_popular_stored(context: str, *, entries: Sequence[dict[str, Any]]) -> None:
    slug = redis_popular_key_slug(context)
    top_names = [_truncate(str(e.get("name", "?")), 24) for e in entries[:8]]
    scores = [e.get("score") for e in entries[:8]]
    _LOG.info(
        "[ingestion-digest] popular_stored runner_context=%r redis=json:popular:%s entries=%d "
        "sample_names_scores=%s",
        context,
        slug,
        len(entries),
        list(zip(top_names, scores)),
    )


def log_popular_empty(context: str, *, reason: str = "no_candidates_or_below_threshold") -> None:
    slug = redis_popular_key_slug(context)
    _LOG.warning(
        "[ingestion-digest] popular_skip runner_context=%r redis_would_be=popular:%s reason=%s "
        "(키 미갱신 — 기존 TTL 데이터만 유지)",
        context,
        slug,
        reason,
    )


def log_batch_summary(job: str, *, ok: int, failed: int, skipped: int = 0, detail: list[dict]) -> None:
    _LOG.info(
        "[ingestion-digest] batch_done job=%r ok=%d skipped=%d failed=%d detail=%s",
        job,
        ok,
        skipped,
        failed,
        detail,
    )
