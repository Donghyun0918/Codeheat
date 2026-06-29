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

# 마커 탐지는 2단계로 한다:
#   1) '진짜 주석'만 추린다 — Pygments로 토큰화해 Comment 토큰만 본다. 이렇게 하면
#      코드 문자열 리터럴 속 가짜 주석이나 docstring 산문이 원천 제외된다.
#      Pygments 미설치/렉서 미존재 시엔 전체 라인을 보는 폴백으로 우아하게 강등한다(_iter_comment_lines).
#   2) 그 라인 안에서 실제 마커 형태인지 본다 — TODO_PATTERN.
# 마커 규칙 (TODO_PATTERN):
#   - 단어 경계(\b): 'todos', 'TODO_PATTERN' 같은 식별자 오탐 제거.
#   - 앵커: 마커가 (주석 시작 토큰 뒤 | 라인 맨 앞) 에 와야 한다. 주석 토큰 텍스트는
#     '#' 로 시작하므로 주석 분기로 매칭되고, 주석 중간에 박힌 산문은
#     걸리지 않는다(마커가 주석 시작 직후가 아니므로).
#   - 두 앵커의 엄격도 차이: 주석 분기는 콜론 선택(콜론 없는 형태도 허용), 라인-시작 분기는
#     콜론 필수(폴백 경로에서 'todo.age = ...' 코드 문장이 오인되는 것 방지).
_TODO_MARKERS = r"TODO|FIXME"
# 주석 시작 토큰: # //  /*  <!--  --(SQL/Lua)  ;(lisp/asm)  %(tex)  *(블록주석 연속줄)
_COMMENT_OPENERS = r"\#|//|/\*|<!--|--|;+|%|\*"
_MARKER = r"(?:" + _TODO_MARKERS + r")\b(?:\([^)\n]*\))?"  # 마커 + 단어경계 + 선택 (작성자)
TODO_PATTERN = re.compile(
    r"(?:(?:" + _COMMENT_OPENERS + r")+\s*" + _MARKER + r"\s*:?\s*"  # 주석 안: ':' 선택
    r"|^\s*" + _MARKER + r"\s*:)",                                   # 라인 시작: ':' 필수
    re.IGNORECASE,
)

# 폴백(Pygments 없음) 경로에서 라인의 문자열 리터럴 구간을 마스킹하기 위한 패턴.
# 토큰화를 못 하므로, 한 줄 안의 따옴표 구간을 공백으로 지워 그 안에 들어간 가짜
# 주석 마커가 매칭되지 않게 한다. 삼중따옴표 → 일반따옴표 → 백틱 순으로
# 시도하고, 백슬래시 이스케이프를 인식한다. 라인 단위라 여러 줄에 걸친
# 문자열은 추적 못 함(폴백의 잔여 한계). 주류 언어는 Pygments 경로라 해당 없음.
_STRING_SPAN = re.compile(
    r'"""(?:\\.|[^\\])*?"""'      # 삼중 큰따옴표
    r"|'''(?:\\.|[^\\])*?'''"     # 삼중 작은따옴표
    r'|"(?:\\.|[^"\\])*"'         # 큰따옴표
    r"|'(?:\\.|[^'\\])*'"         # 작은따옴표
    r"|`(?:\\.|[^`\\])*`"         # 백틱(JS/Go 등)
)


def _mask_strings(line: str) -> str:
    """라인의 문자열 리터럴 구간을 같은 길이의 공백으로 치환."""
    return _STRING_SPAN.sub(lambda m: " " * len(m.group(0)), line)


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


def _iter_comment_lines(src: str, file_path: str):
    """(라인번호, 매칭용텍스트, 표시용텍스트)를 산출.

    - Pygments 경로: 토큰화해 Comment 토큰만 골라낸다. 문자열 리터럴 속 가짜 주석과
      docstring 산문이 토큰 종류 자체로 원천 배제된다. (매칭=표시=주석 텍스트)
    - 폴백 경로(Pygments 미설치/렉서 미존재/렉싱 실패): 전체 라인을 보되, 매칭용
      텍스트는 문자열 리터럴을 마스킹한 버전을 쓴다. 한 줄짜리 가짜 주석을 거른다.
      (표시용은 원본 라인 유지)
    """
    def _fallback():
        # 문자열 리터럴을 마스킹한 텍스트로 매칭하되, 표시는 원본 라인을 쓴다.
        for lineno, line in enumerate(src.splitlines(), start=1):
            yield lineno, _mask_strings(line), line

    try:
        from pygments.lexers import get_lexer_for_filename
        from pygments.token import Comment
    except ImportError:
        yield from _fallback()
        return

    try:
        lexer = get_lexer_for_filename(file_path)
        tokens = list(lexer.get_tokens_unprocessed(src))
    except Exception:  # noqa: BLE001 - 렉서 미존재(ClassNotFound)/렉싱 실패 시 폴백
        yield from _fallback()
        return

    for index, ttype, value in tokens:
        if ttype in Comment:
            start_line = src.count("\n", 0, index) + 1
            for offset, line in enumerate(value.splitlines()):
                yield start_line + offset, line, line


def find_todos(file_path: str) -> list[TodoItem]:
    """파일의 '진짜 주석'에서 TODO/FIXME 마커를 탐지.

    Pygments 토큰화로 주석만 추린 뒤(가능 시) TODO_PATTERN으로 마커 형태를 확인한다.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except (OSError, UnicodeError):
        return []

    todos: list[TodoItem] = []
    for lineno, scan_text, display_text in _iter_comment_lines(src, file_path):
        if TODO_PATTERN.search(scan_text):
            todos.append(
                TodoItem(line=lineno, text=display_text.strip(), age_days=None)
            )
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
