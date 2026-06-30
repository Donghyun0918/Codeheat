"""1단계 보조 지표: 파일 내부 중복률(duplication_ratio).

코드 클론(복붙)이 많은 파일은 한 곳을 고치면 같은 버그가 여러 군데 남는,
리팩토링 부담이 큰 파일이다. 그 부담을 0~1 비율로 수치화한다.

설계 선택 — **순수 파이썬 + Pygments**(외부 도구/Node 없음):
- jscpd 같은 Node 클론 탐지기 대신, 이미 의존성인 Pygments로 토큰화해
  자체 구현한다. ollama 백엔드가 stdlib만 쓰는 것과 같은 "무거운 의존성 0" 철학.
- **type-2 클론**까지 잡는다: 토큰을 정규화(식별자→N, 숫자→0, 문자열→S)하므로
  변수명만 바꾼 복붙도 중복으로 인식한다. 주석/공백은 제외한다.
- Pygments 미설치/렉서 미존재/렉싱 실패 시엔 공백만 정규화하는 라인 폴백
  (type-1 클론만 탐지)으로 우아하게 강등한다 — static_scan의 TODO 탐지와 같은 정책.

정의: 연속 `window`줄(논리 라인 기준)짜리 블록이 파일 안에서 2번 이상 나타나면
그 블록이 덮는 논리 라인들을 '중복'으로 본다. duplication_ratio =
(중복 논리 라인 수) / (전체 논리 라인 수). 빈 줄/주석은 논리 라인에서 제외.
"""

from __future__ import annotations

from collections import defaultdict

# 중복으로 인정할 최소 연속 라인 수. 너무 작으면(1~2) 흔한 한 줄(`return`,
# `}` 등)이 과탐되고, 너무 크면 짧은 복붙을 놓친다. 4가 균형점.
_WINDOW = 4

# window join 구분자 — 정규화 토큰 문자열에 등장하지 않을 제어문자.
_SEP = "␟"


def _fallback_lines(src: str) -> list[tuple[int, str]]:
    """폴백: 공백만 정규화한 비어있지 않은 라인 (type-1 클론용)."""
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if stripped:
            out.append((lineno, stripped))
    return out


def normalized_logical_lines(src: str, file_path: str) -> list[tuple[int, str]]:
    """(라인번호, 정규화 문자열) 목록. 주석/공백 줄은 제외.

    Pygments 경로에선 식별자/숫자/문자열을 placeholder로 정규화해 type-2 클론을
    잡는다. 토큰화 불가 시 _fallback_lines로 강등.
    """
    try:
        from pygments.lexers import get_lexer_for_filename
        from pygments.token import Comment, Name, Number, String
    except ImportError:
        return _fallback_lines(src)

    try:
        lexer = get_lexer_for_filename(file_path)
        tokens = list(lexer.get_tokens(src))
    except Exception:  # noqa: BLE001 - 렉서 미존재/렉싱 실패는 폴백
        return _fallback_lines(src)

    by_line: dict[int, list[str]] = defaultdict(list)
    lineno = 1
    for ttype, value in tokens:
        # 토큰 값이 여러 줄에 걸칠 수 있으므로 줄 단위로 쪼개 분배한다.
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                lineno += 1
            if ttype in Comment:
                continue
            stripped = part.strip()
            if not stripped:
                continue
            if ttype in Name:
                norm = "N"
            elif ttype in Number:
                norm = "0"
            elif ttype in String:
                norm = "S"
            else:
                norm = stripped
            by_line[lineno].append(norm)

    return [(ln, "".join(toks)) for ln, toks in sorted(by_line.items()) if toks]


def duplication_ratio(src: str, file_path: str, window: int = _WINDOW) -> float:
    """파일 내부 중복률(0.0~1.0). 네트워크/IO 없음(순수 계산)."""
    lines = normalized_logical_lines(src, file_path)
    n = len(lines)
    if n < window:
        return 0.0

    # 연속 window줄 블록의 해시 → 시작 인덱스들.
    starts_by_block: dict[str, list[int]] = defaultdict(list)
    for i in range(n - window + 1):
        block = _SEP.join(s for _, s in lines[i : i + window])
        starts_by_block[block].append(i)

    duplicated: set[int] = set()
    for occurrences in starts_by_block.values():
        if len(occurrences) > 1:  # 같은 블록이 2번 이상 → 중복
            for start in occurrences:
                duplicated.update(range(start, start + window))

    return round(len(duplicated) / n, 3)


def compute_duplication(file_path: str) -> float:
    """파일을 읽어 중복률을 계산. 읽기 실패 시 0.0."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except (OSError, UnicodeError):
        return 0.0
    return duplication_ratio(src, file_path)
