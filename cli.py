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
