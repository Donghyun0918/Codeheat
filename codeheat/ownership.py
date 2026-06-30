"""2단계 오너십 분석.

철학: 책임 추궁(blame)이 아니라 **"누가 이 코드를 가장 잘 해결할 수
있나(매칭)"**. 단순 최다 수정자가 아니라 **복잡도가 급증한 시점에 커밋한 사람**
에게 가중치를 준다.

기여자 점수 = Σ (최근성 가중치 × 변화량 가중치)
  - 최근성 가중치: 오래된 커밋일수록 감쇠 (half-life 1년)
  - 변화량 가중치: 그 커밋이 파일 복잡도를 얼마나 끌어올렸나(델타).
    복잡도 델타를 계산할 수 없으면(언어 미지원·git show 실패) churn(변경 라인)으로 대체.

동일인 식별: 기여자는 표시 이름(`%aN`)이 아니라 **이메일(`%aE`)** 로 합산한다.
둘 다 `.mailmap`을 반영하므로, 레포에 mailmap을 두면 한 사람이 여러 이름/메일로
쪼개지지 않는다. 표시 이름은 그 이메일의 **가장 최근 커밋** 이름을 쓴다.
머지 커밋(`--no-merges`)은 churn/점수를 왜곡하므로 집계에서 제외한다.

LLM 레이어로는 이름/점수/메타데이터만 넘어간다(코드 본문 금지). FileOwnershipReport
구조도 이를 따른다.
"""

from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

import lizard

from .models import ContributorScore, FileOwnershipReport

_GIT_TIMEOUT = 30  # seconds
# 최근성 감쇠 반감기. 1년 전 커밋의 가중치는 절반.
_RECENCY_HALFLIFE_DAYS = 365.0


@dataclass
class _Commit:
    """파일을 건드린 커밋 한 건 (분석 내부용)."""

    hash: str
    author: str  # 표시 이름 (%aN, mailmap 반영)
    email: str  # 동일인 합산 키 (%aE, mailmap 반영, 소문자)
    timestamp: int
    churn: int  # added + deleted lines (binary/미상이면 0)
    path: str  # --follow 추적상 그 시점의 경로


def _run_git(repo_path: str, args: list[str]) -> str | None:
    """git 서브커맨드 실행. 실패/타임아웃 시 None."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def get_commit_history(repo_path: str, file_path: str) -> list[_Commit]:
    """파일의 커밋 히스토리를 churn과 함께 수집 (오래된 → 최신 순).

    `git log --no-merges --follow --numstat --format=%H|%aN|%aE|%at` 한 번으로
    메타데이터와 변경량을 함께 파싱한다. `%aN`/`%aE`는 `.mailmap`을 반영한다.
    """
    rel = os.path.relpath(file_path, repo_path)
    out = _run_git(
        repo_path,
        [
            "log",
            "--no-merges",
            "--follow",
            "--numstat",
            "--format=%H|%aN|%aE|%at",
            "--",
            rel,
        ],
    )
    if not out:
        return []

    commits: list[_Commit] = []
    cur: _Commit | None = None
    for line in out.splitlines():
        if not line.strip():
            continue
        if "|" in line and "\t" not in line:
            # 헤더 라인: <hash>|<name>|<email>|<timestamp>
            parts = line.split("|")
            # 이름에 '|'가 들어갈 수 있으니 고정 위치(hash=처음, email/ts=끝)를
            # 기준으로 자르고, 가운데를 이름으로 되붙인다.
            try:
                ts = int(parts[-1])
            except ValueError:
                cur = None
                continue
            cur = _Commit(
                hash=parts[0],
                author="|".join(parts[1:-2]),
                email=parts[-2].strip().lower(),
                timestamp=ts,
                churn=0,
                path=rel,
            )
            commits.append(cur)
        elif "\t" in line and cur is not None:
            # numstat 라인: <added>\t<deleted>\t<path>
            added_s, deleted_s, *rest = line.split("\t")
            added = int(added_s) if added_s.isdigit() else 0
            deleted = int(deleted_s) if deleted_s.isdigit() else 0
            cur.churn += added + deleted
            if rest:
                cur.path = rest[-1]

    commits.reverse()  # git log는 최신순 → 시간순(오래된→최신)으로 뒤집는다
    return commits


def _max_ccn_at(repo_path: str, commit_hash: str, path: str) -> int | None:
    """특정 커밋 시점의 파일을 꺼내 lizard로 최대 CCN 계산. 실패 시 None.

    `analyze_source_code`로 문자열을 바로 분석한다(임시파일 IO 없음). 파일별
    커밋마다 호출되는 핫패스라, 디스크 쓰기/삭제를 없애 비용을 크게 줄인다.
    언어 판별은 `path`의 확장자로 한다.
    """
    content = _run_git(repo_path, ["show", f"{commit_hash}:{path}"])
    if content is None:
        return None
    try:
        info = lizard.analyze_file.analyze_source_code(path, content)
    except Exception:  # noqa: BLE001 - 렉서 미지원/파싱 실패는 폴백(None)으로
        return None
    return max(
        (fn.cyclomatic_complexity for fn in info.function_list), default=0
    )


def _recency_weight(timestamp: int, now: datetime) -> float:
    age_days = max((now - datetime.fromtimestamp(timestamp, tz=timezone.utc)).days, 0)
    return 0.5 ** (age_days / _RECENCY_HALFLIFE_DAYS)


def compute_ownership(
    repo_path: str,
    file_path: str,
    top_n: int = 2,
    use_complexity_delta: bool = True,
) -> FileOwnershipReport:
    """파일 하나의 오너십 리포트 생성."""
    rel = os.path.relpath(file_path, repo_path)
    commits = get_commit_history(repo_path, file_path)
    if not commits:
        return FileOwnershipReport(file=rel, total_commits=0, top_contributors=[])

    now = datetime.now(tz=timezone.utc)
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    last_ts: dict[str, int] = {}
    display_name: dict[str, str] = {}  # 이메일 키 → 가장 최근 커밋의 표시 이름

    prev_ccn: int = 0  # 시간순 진행하며 직전 시점 복잡도 추적
    for commit in commits:  # 오래된 → 최신
        key = commit.email or commit.author.strip().lower()
        # 변화량 가중치: 복잡도 델타(급증분)를 우선, 못 구하면 churn 폴백.
        # churn이 0이면(순수 리네임 등) 내용 변화가 없어 CCN도 그대로이니
        # 비싼 git show를 건너뛰고 폴백 가중치(=1.0)를 쓴다.
        change_weight: float
        if use_complexity_delta and commit.churn != 0:
            after = _max_ccn_at(repo_path, commit.hash, commit.path)
            if after is not None:
                change_weight = 1.0 + max(0, after - prev_ccn)
                prev_ccn = after
            else:
                change_weight = 1.0 + math.log1p(commit.churn)
        else:
            change_weight = 1.0 + math.log1p(commit.churn)

        commit_score = _recency_weight(commit.timestamp, now) * change_weight
        scores[key] = scores.get(key, 0.0) + commit_score
        counts[key] = counts.get(key, 0) + 1
        if commit.timestamp >= last_ts.get(key, 0):
            last_ts[key] = commit.timestamp
            display_name[key] = commit.author  # 최신 커밋 기준 표시 이름

    contributors = [
        ContributorScore(
            name=display_name[key],
            score=round(score, 4),
            commit_count=counts[key],
            last_commit_days=max(
                (now - datetime.fromtimestamp(last_ts[key], tz=timezone.utc)).days,
                0,
            ),
        )
        for key, score in scores.items()
    ]
    contributors.sort(key=lambda c: c.score, reverse=True)

    return FileOwnershipReport(
        file=rel,
        total_commits=len(commits),
        top_contributors=contributors[:top_n],
    )


def build_ownership_reports(
    repo_path: str,
    files: list[str],
    top_n: int = 2,
    use_complexity_delta: bool = True,
) -> list[FileOwnershipReport]:
    """여러 파일의 오너십 리포트를 생성. 입력 파일 순서를 보존한다."""
    return [
        compute_ownership(repo_path, f, top_n=top_n, use_complexity_delta=use_complexity_delta)
        for f in files
    ]


def list_tracked_files(repo_path: str) -> list[str]:
    """git이 추적 중인 파일 목록 (--from-report 미지정 시 fallback)."""
    out = _run_git(repo_path, ["ls-files"])
    if not out:
        return []
    return [ln for ln in out.splitlines() if ln.strip()]
