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
