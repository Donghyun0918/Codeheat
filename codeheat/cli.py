"""CodeHeat CLI 진입점: `codeheat scan|own <path>`."""

from __future__ import annotations

import argparse
import json
import sys

from .ownership import build_ownership_reports, list_tracked_files
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


def _resolve_files(args: argparse.Namespace) -> list[str]:
    """오너십 분석 대상 파일 목록 결정.

    --from-report 가 있으면 1단계 리포트의 파일을(복잡도 내림차순) 사용,
    없으면 git 추적 파일 전체. 둘 다 --limit 로 상한.
    """
    if args.from_report:
        with open(args.from_report, "r", encoding="utf-8") as fh:
            report = json.load(fh)
        files = [f["file"] for f in report.get("files", [])]
    else:
        files = list_tracked_files(args.repo_path)
    if args.limit and args.limit > 0:
        files = files[: args.limit]
    return files


def _cmd_own(args: argparse.Namespace) -> int:
    files = _resolve_files(args)
    if not files:
        print("분석할 파일이 없습니다. (git 저장소인지, --from-report 경로가 맞는지 확인)")
        return 1

    reports = build_ownership_reports(
        args.repo_path,
        files,
        top_n=args.top,
        use_complexity_delta=not args.churn_only,
    )

    payload = {
        "repo_path": args.repo_path,
        "weighting": "churn" if args.churn_only else "complexity_delta",
        "file_count": len(reports),
        "files": [r.to_dict() for r in reports],
    }
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    analyzed = sum(1 for r in reports if r.total_commits > 0)
    print(f"분석한 파일 수: {len(reports)} (git 히스토리 있음: {analyzed})")
    for r in reports[:3]:
        if r.top_contributors:
            top = r.top_contributors[0]
            print(
                f"  {r.file} → {top.name} "
                f"(score={top.score}, commits={top.commit_count}, "
                f"last={top.last_commit_days}d ago)"
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

    own = sub.add_parser(
        "own", help="오너십 분석(복잡도 급증 시점 기여자 매칭) 실행"
    )
    own.add_argument("repo_path", help="분석할 git 저장소 경로")
    own.add_argument(
        "--from-report",
        default=None,
        help="1단계 smell_report.json 경로. 지정 시 그 파일들만 분석",
    )
    own.add_argument(
        "--output",
        default="ownership_report.json",
        help="결과 JSON 출력 경로 (기본: ownership_report.json)",
    )
    own.add_argument(
        "--top",
        type=int,
        default=2,
        help="파일별 상위 기여자 수 (기본: 2)",
    )
    own.add_argument(
        "--limit",
        type=int,
        default=30,
        help="분석할 파일 수 상한 (기본: 30, 0이면 무제한)",
    )
    own.add_argument(
        "--churn-only",
        action="store_true",
        help="복잡도 델타 계산 생략, churn(변경 라인)만으로 가중 (속도 우선)",
    )
    own.set_defaults(func=_cmd_own)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
