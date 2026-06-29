"""4단계 출력 레이어 — GitHub Action PR 봇.

PR이 건드린 코드 파일들의 **히트맵 온도(max CCN)** 와 그 변화량(base→head 델타)을
계산해 PR에 코멘트로 단다. 핵심 철학대로 '누가 쌌나(blame)'가 아니라
'누구에게 물어보면 풀리나(매칭)' — 오너십 top 기여자를 "막히면 물어볼 사람"으로
함께 보여준다.

설계 메모:
- 온도/델타는 `ownership._max_ccn_at` 를 그대로 재사용한다. base/head 각 시점의
  파일을 `git show`로 꺼내 메모리에서 lizard 분석(임시파일 IO 없음)하므로,
  새 의존성 없이 1·2단계와 같은 정의의 max CCN을 얻는다.
- 코멘트 게시는 stdlib `urllib` 만 쓴다(ollama 백엔드와 동일 정책, 추가 의존성 0).
- 같은 PR에 push마다 코멘트가 쌓이지 않도록, 숨김 마커(`MARKER`)로 기존 코멘트를
  찾아 갱신(upsert)한다.

진입점:
    python -m codeheat.ci pr-comment [--repo PATH] [--base REF] [--head REF]
                                     [--churn-only] [--no-post] [--output FILE]

GitHub Actions에서는 `GITHUB_EVENT_PATH`/`GITHUB_REPOSITORY`/`GITHUB_TOKEN`에서
PR 컨텍스트를 자동으로 읽는다. 로컬에서는 `--base/--head`를 주고 `--no-post`로
코멘트만 출력해 확인할 수 있다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

import lizard

from .ownership import _max_ccn_at, _run_git, build_ownership_reports

# 갱신(upsert) 대상 코멘트를 식별하는 숨김 마커. 본문 끝에 둔다.
MARKER = "<!-- codeheat:pr-comment -->"
DEFAULT_GITHUB_API = "https://api.github.com"
_HTTP_TIMEOUT = 30  # seconds


@dataclass
class FileHeat:
    """PR이 건드린 파일 한 개의 온도 변화."""

    path: str  # repo 상대경로
    base_ccn: int | None  # base 시점 max CCN. None이면 base에 없던 신규(또는 분석불가)
    head_ccn: int  # head 시점 max CCN
    owner: str | None  # 막히면 물어볼 사람(오너십 top1). 히스토리 없으면 None
    owner_score: float | None

    @property
    def delta(self) -> int | None:
        """온도 변화량. 신규 파일이면 None."""
        if self.base_ccn is None:
            return None
        return self.head_ccn - self.base_ccn

    @property
    def impact(self) -> int:
        """정렬용 영향도. 신규 파일은 전체 복잡도가 곧 추가된 부담이다."""
        d = self.delta
        return d if d is not None else self.head_ccn


# ---------------------------------------------------------------------------
# git: 변경 파일 + 시점별 온도
# ---------------------------------------------------------------------------


def get_changed_files(repo_path: str, base_ref: str, head_ref: str) -> list[str]:
    """PR이 건드린 파일 목록(삭제 제외)을 repo 상대경로로 반환.

    `base...head`(three-dot)는 merge-base 이후 head 쪽 변경만 보므로, base 브랜치에
    쌓인 무관한 커밋을 끌고 오지 않는다. `--diff-filter=d`로 삭제 파일은 뺀다
    (분석할 대상이 없음).
    """
    out = _run_git(
        repo_path,
        ["diff", "--name-only", "--diff-filter=d", f"{base_ref}...{head_ref}"],
    )
    if not out:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _is_code_file(path: str) -> bool:
    """lizard가 복잡도를 잴 수 있는 언어 파일인지. 비코드(.md/.json/.toml 등)는 제외.

    온도(=복잡도) 개념이 없는 파일을 표에서 빼고, 불필요한 오너십·git show
    호출도 건너뛴다.
    """
    return lizard.get_reader_for(path) is not None


def _resolve_sha(repo_path: str, ref: str | None) -> str | None:
    if not ref:
        return None
    out = _run_git(repo_path, ["rev-parse", ref])
    return out.strip() if out else None


def compute_file_heats(
    repo_path: str,
    files: list[str],
    base_ref: str,
    head_ref: str,
    use_complexity_delta: bool = True,
) -> list[FileHeat]:
    """변경 파일별 온도(base/head max CCN)와 오너를 모아 영향도 내림차순 정렬.

    head에서 분석 불가한 파일(비코드/렉서 미지원)은 결과에서 제외한다.
    """
    base_sha = _resolve_sha(repo_path, base_ref)
    head_sha = _resolve_sha(repo_path, head_ref) or "HEAD"

    # 비코드 파일은 온도 개념이 없으니 먼저 거른다(오너십/git show 호출도 절약).
    files = [f for f in files if _is_code_file(f)]

    # 오너십: 변경 파일에 한해 top1 기여자만. 파일 수가 적어(=PR diff) 비용이 작다.
    abs_files = [os.path.join(repo_path, f) for f in files]
    own_reports = build_ownership_reports(
        repo_path, abs_files, top_n=1, use_complexity_delta=use_complexity_delta
    )
    own_by_rel = {os.path.normpath(r.file): r for r in own_reports}

    heats: list[FileHeat] = []
    for rel in files:
        head_ccn = _max_ccn_at(repo_path, head_sha, rel)
        if head_ccn is None:
            continue  # 코드가 아니거나 분석 불가 — 온도 개념이 없다
        base_ccn = _max_ccn_at(repo_path, base_sha, rel) if base_sha else None

        owner = owner_score = None
        report = own_by_rel.get(os.path.normpath(rel))
        if report and report.top_contributors:
            top = report.top_contributors[0]
            owner, owner_score = top.name, top.score

        heats.append(
            FileHeat(
                path=rel,
                base_ccn=base_ccn,
                head_ccn=head_ccn,
                owner=owner,
                owner_score=owner_score,
            )
        )

    heats.sort(key=lambda h: h.impact, reverse=True)
    return heats


# ---------------------------------------------------------------------------
# 코멘트 본문 (순수 함수)
# ---------------------------------------------------------------------------


def _delta_cell(heat: FileHeat) -> str:
    d = heat.delta
    if d is None:
        return "🆕 신규"
    if d > 0:
        return f"🔺 +{d}"
    if d < 0:
        return f"🔻 {d}"
    return "▪️ ±0"


def _owner_cell(heat: FileHeat) -> str:
    if not heat.owner:
        return "— (히스토리 부족)"
    return f"{heat.owner} (점수 {heat.owner_score})"


def build_comment(heats: list[FileHeat]) -> str:
    """FileHeat 목록을 PR 코멘트 마크다운으로 직렬화. 네트워크/IO 없음."""
    if not heats:
        return (
            "## 🔥 CodeHeat\n\n"
            "이 PR에서 분석할 코드 변경이 없습니다(또는 대상 파일이 비코드입니다).\n\n"
            f"<sub>CodeHeat · \"누가 쌌나(blame)\"가 아니라 \"누가 해결할 수 있나(매칭)\"</sub>\n"
            f"{MARKER}\n"
        )

    lines = [
        "## 🔥 CodeHeat — 이 PR의 복잡도 영향",
        "",
        f"이 PR이 건드린 코드 파일 **{len(heats)}개**의 히트맵 온도(max CCN) 변화입니다. "
        "온도가 오른 파일일수록 리팩토링 부담이 커집니다 — 막히면 \"물어볼 사람\"에게 물어보세요.",
        "",
        "| 파일 | 온도 | 변화 | 막히면 물어볼 사람 |",
        "| --- | ---: | --- | --- |",
    ]
    for h in heats:
        lines.append(
            f"| `{h.path}` | {h.head_ccn} | {_delta_cell(h)} | {_owner_cell(h)} |"
        )

    hottest = heats[0]
    lines.append("")
    if hottest.impact > 0:
        who = hottest.owner or "해당 파일 오너"
        lines.append(
            f"> 🌡️ 가장 뜨거워진 파일: **`{hottest.path}`** "
            f"({_delta_cell(hottest)}). 리팩토링 전에 **{who}** 에게 물어보세요."
        )
    else:
        lines.append("> ✅ 이 PR로 더 뜨거워진 코드 파일은 없습니다. 👍")

    lines.append("")
    lines.append(
        "<sub>CodeHeat · \"누가 쌌나(blame)\"가 아니라 \"누가 해결할 수 있나(매칭)\"</sub>"
    )
    lines.append(MARKER)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# GitHub API (stdlib urllib)
# ---------------------------------------------------------------------------


def _github_request(method: str, url: str, token: str, body: dict | None = None):
    """GitHub REST 호출. 추가 의존성 없이 urllib만 사용."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _find_existing_comment(api: str, repo: str, pr: int, token: str) -> int | None:
    """MARKER가 담긴 기존 CodeHeat 코멘트 id를 찾는다(없으면 None)."""
    page = 1
    while True:
        url = f"{api}/repos/{repo}/issues/{pr}/comments?per_page=100&page={page}"
        comments = _github_request("GET", url, token)
        if not comments:
            return None
        for c in comments:
            if MARKER in (c.get("body") or ""):
                return c["id"]
        if len(comments) < 100:
            return None
        page += 1


def upsert_comment(api: str, repo: str, pr: int, token: str, body: str) -> str:
    """기존 CodeHeat 코멘트가 있으면 갱신, 없으면 생성. 동작 결과 문자열 반환."""
    existing = _find_existing_comment(api, repo, pr, token)
    if existing is not None:
        _github_request(
            "PATCH", f"{api}/repos/{repo}/issues/comments/{existing}", token, {"body": body}
        )
        return "updated"
    _github_request(
        "POST", f"{api}/repos/{repo}/issues/{pr}/comments", token, {"body": body}
    )
    return "created"


# ---------------------------------------------------------------------------
# PR 컨텍스트 해석 (GitHub Actions 환경변수/이벤트 페이로드)
# ---------------------------------------------------------------------------


def _load_event() -> dict:
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_pr_context(args: argparse.Namespace) -> tuple[str | None, str, int | None, str | None]:
    """(base_ref, head_ref, pr_number, repo_slug) 결정.

    우선순위: CLI 인자 > pull_request 이벤트 페이로드 > 기타 GITHUB_* 환경변수.
    head는 끝내 못 구하면 "HEAD"로 둔다(체크아웃된 작업트리 기준).
    """
    event = _load_event()
    pr = event.get("pull_request") or {}

    base = args.base or pr.get("base", {}).get("sha")
    if not base and os.environ.get("GITHUB_BASE_REF"):
        # fetch-depth:0 체크아웃이면 origin/<base_branch>가 잡힌다.
        base = f"origin/{os.environ['GITHUB_BASE_REF']}"

    head = args.head or pr.get("head", {}).get("sha") or "HEAD"
    number = args.pr or pr.get("number") or event.get("number")
    repo_slug = args.repo_slug or os.environ.get("GITHUB_REPOSITORY")
    return base, head, number, repo_slug


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_pr_comment(args: argparse.Namespace) -> int:
    base, head, number, repo_slug = resolve_pr_context(args)
    if not base:
        print(
            "base 레퍼런스를 정할 수 없습니다. --base 로 지정하거나 "
            "GitHub Actions의 pull_request 이벤트에서 실행하세요.",
            file=sys.stderr,
        )
        return 1

    files = get_changed_files(args.repo, base, head)
    heats = compute_file_heats(
        args.repo, files, base, head, use_complexity_delta=not args.churn_only
    )
    body = build_comment(heats)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(body)
    print(body)

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if args.no_post:
        print("[--no-post] 코멘트 게시를 건너뜁니다.", file=sys.stderr)
        return 0
    if not (token and repo_slug and number):
        print(
            "코멘트 게시를 건너뜁니다(GITHUB_TOKEN/GITHUB_REPOSITORY/PR 번호 중 일부 없음). "
            "본문은 위 출력 참고.",
            file=sys.stderr,
        )
        return 0

    api = os.environ.get("GITHUB_API_URL", DEFAULT_GITHUB_API).rstrip("/")
    try:
        result = upsert_comment(api, repo_slug, int(number), token, body)
    except urllib.error.URLError as e:
        print(f"코멘트 게시 실패: {e}", file=sys.stderr)
        return 1
    print(f"코멘트 {result}: {repo_slug} #{number}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codeheat-ci",
        description="CodeHeat GitHub Action PR 봇 — PR의 복잡도 온도 변화를 코멘트로 단다",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("pr-comment", help="PR 변경 파일의 온도 변화 코멘트 생성/게시")
    pc.add_argument("--repo", default=".", help="git 저장소 경로 (기본: 현재 디렉토리)")
    pc.add_argument("--base", default=None, help="비교 기준 ref (미지정 시 PR base)")
    pc.add_argument("--head", default=None, help="대상 ref (미지정 시 PR head 또는 HEAD)")
    pc.add_argument("--pr", type=int, default=None, help="PR 번호 (미지정 시 이벤트에서)")
    pc.add_argument(
        "--repo-slug", default=None, help="owner/repo (미지정 시 GITHUB_REPOSITORY)"
    )
    pc.add_argument(
        "--churn-only",
        action="store_true",
        help="오너십 점수에서 복잡도 델타 생략, churn만 사용 (속도 우선)",
    )
    pc.add_argument("--output", default=None, help="코멘트 마크다운을 파일로도 저장")
    pc.add_argument(
        "--no-post",
        action="store_true",
        help="코멘트를 게시하지 않고 본문만 출력 (로컬 확인용)",
    )
    pc.set_defaults(func=_cmd_pr_comment)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
