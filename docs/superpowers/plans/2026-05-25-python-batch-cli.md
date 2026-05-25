# Python Batch CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pet-data-api를 FastAPI 서버 없이 CLI로 실행 가능한 배치 파이프라인으로 전환 — `python cli.py popular --output /data/locations.json` 하나로 네이버 수집 → LocationImportDto JSON 파일 출력.

**Architecture:** 기존 ingestion 함수(blog.py, local_discovery.py, location.py)를 그대로 재사용하되 Redis 저장 단계를 건너뛴다. `app/ingestion/exporter.py`가 수집 결과를 `LocationImportDto` dict로 변환하고, `cli.py`가 argparse → asyncio.run → JSON 파일 쓰기를 담당한다.

**Tech Stack:** Python 3.11+, asyncio, argparse, pytest, pytest-asyncio, unittest.mock

---

## 코드베이스 핵심 사실 (읽기 전에 숙지)

```
app/ingestion/runner.py        — _POPULAR_CONTEXTS, _LOCAL_DISCOVERY_CONTEXTS 정의
app/ingestion/blog.py          — collect_popular_for_context(context) → list[dict]
app/ingestion/local_discovery.py — collect_popular_local_discovery(context) → list[dict]
app/ingestion/location.py      — enrich_with_location(entries, context) → list[dict]
```

`run_popular_collection()` 흐름 (runner.py:82-110):
```python
for context in _POPULAR_CONTEXTS:
    if context in _LOCAL_DISCOVERY_CONTEXTS:          # boarding, hotel
        popular = await collect_popular_local_discovery(context)   # 위치 정보 이미 포함
    else:
        popular = await collect_popular_for_context(context)
        popular = await enrich_with_location(popular, context)     # 위치 정보 보강
    await save_popular(context, popular)               # ← Redis 저장 (CLI에서 스킵)
```

수집 결과 dict 키 (두 경로 공통):
- `name`, `score`, `address`, `road_address`, `map_x`, `map_y`, `telephone`
- `map_x` = Naver mapx 문자열 (경도 × 10^7), `map_y` = Naver mapy 문자열 (위도 × 10^7)

`LocationImportDto` 필드 (Spring쪽 이미 구현됨):
`name, category, address, sido, sigungu, lat, lng, phone, status`

---

## 파일 맵

| 작업 | 파일 |
|------|------|
| 생성 | `app/ingestion/exporter.py` |
| 생성 | `tests/test_exporter.py` |
| 생성 | `cli.py` (프로젝트 루트) |
| 생성 | `tests/test_cli.py` |

---

## Task 1: exporter.py — 변환 헬퍼 + 수집 함수

**Files:**
- Create: `app/ingestion/exporter.py`

- [ ] **Step 1: 파일 생성**

```python
"""
popular 수집 결과를 LocationImportDto dict로 변환하고 일괄 수집하는 모듈.
Redis 의존 없음 — CLI / cron 전용.
"""
import logging
from typing import Optional

from app.ingestion.blog import collect_popular_for_context
from app.ingestion.local_discovery import collect_popular_local_discovery
from app.ingestion.location import enrich_with_location

_log = logging.getLogger(__name__)

POPULAR_CONTEXTS: list[str] = [
    "grooming", "hospital", "supplies", "pharmacy",
    "cafe", "pension", "restaurant", "boarding", "hotel",
]
_LOCAL_DISCOVERY_CONTEXTS: frozenset[str] = frozenset({"boarding", "hotel"})


def _coord(val: Optional[str]) -> Optional[float]:
    """Naver mapx/mapy 문자열(위도·경도 × 10^7)을 소수점 도(°) 좌표로 변환."""
    if not val:
        return None
    try:
        v = float(val)
        return v / 1e7 if v != 0 else None
    except (ValueError, TypeError):
        return None


def parse_address_parts(address: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """주소 문자열의 첫 두 토큰을 sido, sigungu로 반환."""
    if not address:
        return None, None
    parts = address.split()
    return (parts[0] if parts else None), (parts[1] if len(parts) > 1 else None)


def popular_dict_to_dto(d: dict, category: str) -> dict:
    """수집 결과 dict → LocationImportDto dict 변환."""
    address = d.get("road_address") or d.get("address")
    sido, sigungu = parse_address_parts(address)
    return {
        "name":     d["name"],
        "category": category,
        "address":  address,
        "sido":     sido,
        "sigungu":  sigungu,
        "lat":      _coord(d.get("map_y")),
        "lng":      _coord(d.get("map_x")),
        "phone":    d.get("telephone"),
        "status":   "운영중",
    }


async def collect_popular_for_cli(contexts: list[str]) -> list[dict]:
    """
    popular 수집 파이프라인 실행 — Redis 저장 없이 LocationImportDto list 반환.
    runner.run_popular_collection()과 동일 로직에서 save_popular() 호출만 제거.
    """
    result: list[dict] = []
    for context in contexts:
        try:
            if context in _LOCAL_DISCOVERY_CONTEXTS:
                entries = await collect_popular_local_discovery(context)
            else:
                entries = await collect_popular_for_context(context)
                if entries:
                    entries = await enrich_with_location(entries, context)
            dtos = [popular_dict_to_dto(e, context) for e in entries if e.get("name")]
            _log.info("exporter context=%s count=%d", context, len(dtos))
            result.extend(dtos)
        except Exception as e:
            _log.error("exporter failed context=%s err=%s", context, e)
    return result
```

- [ ] **Step 2: 임포트 확인**

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate
python -c "from app.ingestion.exporter import collect_popular_for_cli, POPULAR_CONTEXTS; print('ok')"
```

Expected: `ok`

---

## Task 2: test_exporter.py — 변환 헬퍼 단위 테스트

**Files:**
- Create: `tests/test_exporter.py`

- [ ] **Step 1: 테스트 파일 작성**

```python
import pytest
from app.ingestion.exporter import _coord, parse_address_parts, popular_dict_to_dto


# ── _coord ────────────────────────────────────────────────────────────

def test_coord_converts_naver_mapy_to_lat():
    assert _coord("375000000") == pytest.approx(37.5)


def test_coord_converts_naver_mapx_to_lng():
    assert _coord("1270000000") == pytest.approx(127.0)


def test_coord_returns_none_for_empty_string():
    assert _coord("") is None


def test_coord_returns_none_for_none():
    assert _coord(None) is None


def test_coord_returns_none_for_zero():
    assert _coord("0") is None


# ── parse_address_parts ───────────────────────────────────────────────

def test_parse_address_parts_standard():
    sido, sigungu = parse_address_parts("서울특별시 강남구 테헤란로 123")
    assert sido == "서울특별시"
    assert sigungu == "강남구"


def test_parse_address_parts_none_input():
    assert parse_address_parts(None) == (None, None)


def test_parse_address_parts_empty_string():
    assert parse_address_parts("") == (None, None)


def test_parse_address_parts_single_token():
    sido, sigungu = parse_address_parts("서울특별시")
    assert sido == "서울특별시"
    assert sigungu is None


# ── popular_dict_to_dto ───────────────────────────────────────────────

def test_popular_dict_to_dto_blog_entry():
    d = {
        "name":         "멍멍미용",
        "mention_count": 3,
        "score":        1.0,
        "address":      "서울특별시 강남구 역삼동 1",
        "road_address": None,
        "map_x":        "1270000000",
        "map_y":        "375000000",
        "telephone":    "02-1234-5678",
    }
    dto = popular_dict_to_dto(d, "grooming")
    assert dto["name"]     == "멍멍미용"
    assert dto["category"] == "grooming"
    assert dto["address"]  == "서울특별시 강남구 역삼동 1"
    assert dto["sido"]     == "서울특별시"
    assert dto["sigungu"]  == "강남구"
    assert dto["lat"]      == pytest.approx(37.5)
    assert dto["lng"]      == pytest.approx(127.0)
    assert dto["phone"]    == "02-1234-5678"
    assert dto["status"]   == "운영중"


def test_popular_dict_to_dto_prefers_road_address():
    d = {
        "name":         "멍멍미용",
        "address":      "서울특별시 강남구 역삼동 1",
        "road_address": "서울특별시 강남구 테헤란로 1",
        "map_x": None, "map_y": None, "telephone": None,
    }
    dto = popular_dict_to_dto(d, "grooming")
    assert dto["address"] == "서울특별시 강남구 테헤란로 1"


def test_popular_dict_to_dto_no_coords():
    d = {
        "name": "멍멍미용", "address": "서울특별시 강남구 역삼동 1",
        "road_address": None, "map_x": None, "map_y": None, "telephone": None,
    }
    dto = popular_dict_to_dto(d, "grooming")
    assert dto["lat"] is None
    assert dto["lng"] is None
```

- [ ] **Step 2: 테스트 실행 — PASS 확인**

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate
PYTHONPATH=. pytest tests/test_exporter.py -v
```

Expected: 13개 모두 PASS

- [ ] **Step 3: 커밋**

```bash
git add app/ingestion/exporter.py tests/test_exporter.py
git commit -m "feat(batch): exporter — popular 수집 결과를 LocationImportDto JSON으로 변환"
```

---

## Task 3: cli.py — argparse 진입점

**Files:**
- Create: `cli.py` (프로젝트 루트 `/Users/maknkkong/project/pet-data-api/cli.py`)

- [ ] **Step 1: 파일 생성**

```python
#!/usr/bin/env python3
"""
pet-data 배치 파이프라인 CLI

사용법:
  python cli.py popular --output /data/locations.json
  python cli.py popular --output /data/locations.json --contexts grooming hospital
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path

from app.ingestion.exporter import POPULAR_CONTEXTS, collect_popular_for_cli

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="pet-data 배치 파이프라인 — JSON 파일 출력"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pop = sub.add_parser("popular", help="인기 시설 수집 → JSON 파일")
    pop.add_argument(
        "--output", required=True, metavar="PATH",
        help="출력 JSON 파일 경로 (예: /data/locations.json)",
    )
    pop.add_argument(
        "--contexts", nargs="*", default=None,
        choices=list(POPULAR_CONTEXTS), metavar="CTX",
        help=f"수집 컨텍스트 (기본: 전체 {list(POPULAR_CONTEXTS)})",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    if args.command == "popular":
        contexts = args.contexts or list(POPULAR_CONTEXTS)
        dicts = asyncio.run(collect_popular_for_cli(contexts))
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(dicts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[cli] popular: {len(dicts)}건 → {output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 임포트 및 --help 확인**

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate
python cli.py --help
```

Expected: `usage: cli.py [-h] {popular} ...` 출력

```bash
python cli.py popular --help
```

Expected: `--output PATH`, `--contexts CTX` 옵션 표시

---

## Task 4: test_cli.py — CLI 스모크 테스트

**Files:**
- Create: `tests/test_cli.py`

- [ ] **Step 1: 테스트 파일 작성**

```python
import json
import sys
from unittest.mock import AsyncMock, patch

import pytest

from cli import _build_parser, main


# ── argparse ─────────────────────────────────────────────────────────

def test_parser_popular_requires_output():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["popular"])  # --output 없으면 SystemExit


def test_parser_popular_parses_output():
    parser = _build_parser()
    args = parser.parse_args(["popular", "--output", "/tmp/out.json"])
    assert args.output == "/tmp/out.json"
    assert args.contexts is None  # 기본값: 전체 수집


def test_parser_popular_parses_contexts():
    parser = _build_parser()
    args = parser.parse_args(["popular", "--output", "/tmp/out.json", "--contexts", "grooming", "hospital"])
    assert args.contexts == ["grooming", "hospital"]


def test_parser_rejects_unknown_context():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["popular", "--output", "/tmp/out.json", "--contexts", "invalid_context"])


# ── main() 통합 ──────────────────────────────────────────────────────

def test_main_writes_json_file(tmp_path, monkeypatch):
    """main()이 JSON 파일을 정상적으로 생성하는지 확인 (Naver API 호출 없음)."""
    output = tmp_path / "locations.json"
    fake_dtos = [
        {"name": "테스트미용", "category": "grooming", "address": "서울특별시 강남구 테헤란로 1",
         "sido": "서울특별시", "sigungu": "강남구", "lat": 37.5, "lng": 127.0,
         "phone": None, "status": "운영중"},
    ]
    monkeypatch.setattr(
        sys, "argv",
        ["cli.py", "popular", "--output", str(output), "--contexts", "grooming"],
    )
    with patch(
        "cli.collect_popular_for_cli",
        new=AsyncMock(return_value=fake_dtos),
    ):
        main()

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["name"] == "테스트미용"
    assert data[0]["status"] == "운영중"


def test_main_creates_parent_directory(tmp_path, monkeypatch):
    """출력 경로의 부모 디렉터리가 없어도 자동 생성."""
    output = tmp_path / "nested" / "dir" / "out.json"
    monkeypatch.setattr(
        sys, "argv",
        ["cli.py", "popular", "--output", str(output), "--contexts", "grooming"],
    )
    with patch("cli.collect_popular_for_cli", new=AsyncMock(return_value=[])):
        main()

    assert output.exists()
```

- [ ] **Step 2: 테스트 실행 — PASS 확인**

```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate
PYTHONPATH=. pytest tests/test_cli.py -v
```

Expected: 6개 모두 PASS

- [ ] **Step 3: 전체 테스트 스위트 확인 (기존 테스트 회귀 없음)**

```bash
PYTHONPATH=. pytest tests/ -v --ignore=tests/test_naver_collector.py 2>&1 | tail -20
```

Expected: `test_exporter.py` 13개 + `test_cli.py` 6개 포함, 기존 테스트 회귀 없음

- [ ] **Step 4: 최종 커밋**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat(batch): cli.py — popular 배치 CLI 진입점 (argparse + JSON 출력)"
```

---

## 검증

### 단위 테스트
```bash
cd /Users/maknkkong/project/pet-data-api
source venv/bin/activate
PYTHONPATH=. pytest tests/test_exporter.py tests/test_cli.py -v
```
Expected: 19개 PASS

### 실제 실행 (Naver API 키 설정 시)
```bash
# .env 파일에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 설정 후
python cli.py popular --output /tmp/test_locations.json --contexts grooming
cat /tmp/test_locations.json | python -m json.tool | head -30
```
