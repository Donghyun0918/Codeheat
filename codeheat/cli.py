"""CodeHeat CLI 진입점: `codeheat scan <path>`."""

from __future__ import annotations

import argparse
import json
import sys

from .static_scan import build_smell_reports


def _cmd_scan(args: argparse.Namespace) -> int:
    reports = build_smell_reports(
        args.repo_path, compute_todo_age=not args.no_todo_age
    )

    payload = {
        "repo_path": args.repo_path,
        "file_count": len(reports),
        "files": [r.to_dict() for r in reports],
    }
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    print(f"분석한 파일 수: {len(reports)}")
    if reports:
        top = reports[0]
        print(
            f"가장 복잡한 파일: {top.file} "
            f"(max CCN={top.complexity}, avg={top.avg_complexity}, "
            f"functions={top.function_count})"
        )
    print(f"리포트 저장: {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codeheat",
        description="코드 복잡도 + git 히스토리로 리팩토링 우선순위를 찾는 툴",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="정적 분석(복잡도 + TODO) 실행")
    scan.add_argument("repo_path", help="분석할 저장소/디렉토리 경로")
    scan.add_argument(
        "--output",
        default="smell_report.json",
        help="결과 JSON 출력 경로 (기본: smell_report.json)",
    )
    scan.add_argument(
        "--no-todo-age",
        action="store_true",
        help="git log 기반 TODO 나이 계산 생략 (속도 우선)",
    )
    scan.set_defaults(func=_cmd_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
