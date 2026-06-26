"""1단계 정적 분석: 복잡도(lizard) + TODO/FIXME 탐지 + TODO 나이(git pickaxe)."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone

import lizard

from .models import FileSmellReport, TodoItem

# 스캔에서 제외할 디렉토리. lizard.analyze의 exclude_pattern은 glob이므로
# 경로 어디에 있든 매칭되도록 양쪽에 와일드카드를 둔다.
EXCLUDE_DIRS = ["node_modules", ".git", "venv", ".venv"]
EXCLUDE_PATTERNS = [f"*/{d}/*" for d in EXCLUDE_DIRS]

# 단어 경계(\b)가 핵심. 없으면 `todos`, `TODO_PATTERN` 같은 식별자까지 오탐된다.
# 콜론/공백 뒤 텍스트(있으면)를 함께 캡처한다.
TODO_PATTERN = re.compile(r"\b(?:TODO|FIXME)\b[:\s]*(.*)", re.IGNORECASE)

# git pickaxe에 넘기는 검색 문자열 최대 길이. 너무 길면 공백/특수문자로
# 정확히 안 맞을 위험이 커지므로 앞부분만 사용한다.
_PICKAXE_PREFIX_LEN = 40
_GIT_TIMEOUT = 15  # seconds


def scan_complexity(repo_path: str) -> dict[str, list]:
    """파일별 함수 정보를 lizard로 수집.

    반환: {절대/상대 파일경로: [FunctionInfo, ...]}.
    제외 디렉토리(node_modules/.git/venv/.venv)는 건너뛴다.
    """
    results: dict[str, list] = {}
    # NOTE: 인자명은 exclude_pattern (exclude_pattern_list 아님).
    #       단, glob "리스트"를 받는다. 문자열 하나를 주면 lizard가 그걸
    #       문자 단위로 순회해 '*'가 전부 매칭 → 모든 파일이 제외되는 함정이 있다.
    #       경로 검사(_is_excluded)로 한 번 더 방어한다.
    for file_info in lizard.analyze(
        [repo_path], exclude_pattern=EXCLUDE_PATTERNS
    ):
        if _is_excluded(file_info.filename):
            continue
        results[file_info.filename] = list(file_info.function_list)
    return results


def _is_excluded(path: str) -> bool:
    parts = set(path.replace("\\", "/").split("/"))
    return any(d in parts for d in EXCLUDE_DIRS)


def find_todos(file_path: str) -> list[TodoItem]:
    """파일에서 TODO/FIXME 라인을 정규식으로 탐지."""
    todos: list[TodoItem] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            for lineno, raw in enumerate(fh, start=1):
                match = TODO_PATTERN.search(raw)
                if match:
                    todos.append(
                        TodoItem(line=lineno, text=raw.strip(), age_days=None)
                    )
    except (OSError, UnicodeError):
        return []
    return todos


def get_todo_age_days(
    repo_path: str, file_path: str, line_text: str
) -> int | None:
    """git pickaxe(-S)로 해당 TODO 문자열이 처음 등장한 커밋을 찾아 나이(일) 반환.

    텍스트는 앞 40자만 사용. git 미설치/타임아웃/미추적 파일 등은 None.
    """
    needle = line_text.strip()[:_PICKAXE_PREFIX_LEN]
    if not needle:
        return None

    rel = os.path.relpath(file_path, repo_path)
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                repo_path,
                "log",
                "-S",
                needle,
                "--reverse",
                "--format=%at",
                "--",
                rel,
            ],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if proc.returncode != 0:
        return None

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return None

    try:
        first_ts = int(lines[0])  # --reverse → 첫 줄이 가장 오래된 커밋
    except ValueError:
        return None

    introduced = datetime.fromtimestamp(first_ts, tz=timezone.utc)
    delta = datetime.now(tz=timezone.utc) - introduced
    return max(delta.days, 0)


def build_smell_reports(
    repo_path: str, compute_todo_age: bool = True
) -> list[FileSmellReport]:
    """복잡도 + TODO를 묶어 복잡도 내림차순 정렬된 리포트 리스트 반환."""
    complexity_map = scan_complexity(repo_path)
    reports: list[FileSmellReport] = []

    for file_path, functions in complexity_map.items():
        ccns = [fn.cyclomatic_complexity for fn in functions]
        max_ccn = max(ccns) if ccns else 0
        avg_ccn = round(sum(ccns) / len(ccns), 2) if ccns else 0.0
        loc = sum(fn.nloc for fn in functions)

        todos = find_todos(file_path)
        if compute_todo_age:
            for todo in todos:
                todo.age_days = get_todo_age_days(
                    repo_path, file_path, todo.text
                )

        reports.append(
            FileSmellReport(
                file=os.path.relpath(file_path, repo_path),
                complexity=max_ccn,
                avg_complexity=avg_ccn,
                function_count=len(functions),
                loc=loc,
                todos=todos,
            )
        )

    reports.sort(key=lambda r: r.complexity, reverse=True)
    return reports
