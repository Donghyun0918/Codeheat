"""ownership.py: git 로그 파싱·최근성 가중치·빈 히스토리 처리 검증.

git 서브프로세스는 monkeypatch로 대체해 네트워크/저장소 상태에 의존하지 않는다.
"""

from datetime import datetime, timezone

from codeheat import ownership
from codeheat.ownership import (
    _RECENCY_HALFLIFE_DAYS,
    _changed_line_ranges,
    _recency_weight,
    _touched_max_ccn,
    compute_ownership,
    get_commit_history,
)

# 함수 단위 매칭 테스트용 픽스처: simple()=CCN1(라인1-2), hairy()=CCN4(라인4-10).
_FUNC_SRC = (
    "def simple():\n"          # 1
    "    return 1\n"           # 2
    "\n"                        # 3
    "def hairy(x):\n"          # 4
    "    if x > 0:\n"          # 5
    "        if x > 1:\n"      # 6
    "            return 2\n"   # 7
    "    elif x < 0:\n"        # 8
    "        return -1\n"      # 9
    "    return 0\n"           # 10
)


def _git_with_diffs(log, diffs, content=_FUNC_SRC):
    """args에 따라 log / unified diff / 파일 내용을 돌려주는 가짜 _run_git."""

    def fake(repo, args):
        if args and args[0] == "log":
            return log
        if args and args[0] == "show":
            if "--unified=0" in args:
                commit_hash = args[args.index("--unified=0") + 1]
                return diffs.get(commit_hash, "")
            return content  # "show", "<hash>:<path>"
        return None

    return fake


def test_recency_weight_decays_by_halflife():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 지금 시점 커밋 → 가중치 1.0
    assert _recency_weight(int(now.timestamp()), now) == 1.0
    # 정확히 반감기 전 커밋 → 0.5 근처
    one_halflife_ago = now.timestamp() - _RECENCY_HALFLIFE_DAYS * 86400
    w = _recency_weight(int(one_halflife_ago), now)
    assert abs(w - 0.5) < 0.01


def test_get_commit_history_parses_and_reverses(monkeypatch):
    # git log는 최신→과거 순. churn은 numstat 합. 헤더는 hash|name|email|ts.
    fake_log = (
        "abc123|Alice|alice@example.com|2000000000\n"
        "10\t5\tfile.py\n"
        "def456|Bob Smith|bob@example.com|1000000000\n"
        "3\t2\tfile.py\n"
    )
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: fake_log)

    commits = get_commit_history("/repo", "/repo/file.py")
    # reverse() 적용 → 오래된(Bob) 먼저
    assert [c.author for c in commits] == ["Bob Smith", "Alice"]
    assert [c.email for c in commits] == ["bob@example.com", "alice@example.com"]
    assert commits[0].timestamp == 1000000000
    assert commits[0].churn == 5  # 3 + 2
    assert commits[1].churn == 15  # 10 + 5


def test_get_commit_history_requests_no_merges(monkeypatch):
    # 머지 커밋은 churn/점수를 왜곡하므로 --no-merges로 빠져야 한다.
    seen = {}

    def fake_run_git(repo, args):
        seen["args"] = args
        return "h|N|e@x|1\n1\t0\tfile.py\n"

    monkeypatch.setattr(ownership, "_run_git", fake_run_git)
    get_commit_history("/repo", "/repo/file.py")
    assert "--no-merges" in seen["args"]


def test_get_commit_history_handles_pipe_in_name(monkeypatch):
    # 이름에 '|'가 들어가도 email/ts는 끝에서 고정 위치로 잘려야 한다.
    fake_log = "h1|Od|Bad|Name|weird@example.com|1500000000\n4\t0\tfile.py\n"
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: fake_log)
    commits = get_commit_history("/repo", "/repo/file.py")
    assert commits[0].author == "Od|Bad|Name"
    assert commits[0].email == "weird@example.com"
    assert commits[0].timestamp == 1500000000


def test_get_commit_history_relative_path_outside_cwd(monkeypatch):
    """레포 밖에서 절대 repo_path + 상대 파일경로로 돌려도 git에 올바른 상대경로가 간다.

    옛 버그: relpath('sub/x.py', '/abs/repo')가 cwd 기준 '../../...'로 어긋나
    히스토리 0이 됐다. _rel_to_repo로 repo 기준 정규화한다.
    """
    seen = {}

    def fake_run_git(repo, args):
        seen["args"] = args
        return "h|N|e@x|1\n2\t0\tsub/x.py\n"

    monkeypatch.setattr(ownership, "_run_git", fake_run_git)
    # repo_path는 절대, file_path는 repo 기준 상대 (--from-report가 주는 형태)
    get_commit_history("/abs/repo", "sub/x.py")
    # git 인자 끝의 '-- <path>'가 'sub/x.py'여야 한다 ('../' 끼면 버그)
    assert seen["args"][-1] == "sub/x.py"


def test_get_commit_history_empty_on_no_output(monkeypatch):
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: None)
    assert get_commit_history("/repo", "/repo/file.py") == []


def test_compute_ownership_empty_history(monkeypatch):
    monkeypatch.setattr(ownership, "get_commit_history", lambda repo, f: [])
    report = compute_ownership("/repo", "/repo/missing.py")
    assert report.total_commits == 0
    assert report.top_contributors == []


def test_compute_ownership_churn_only_scores(monkeypatch):
    fake_log = (
        "h1|Alice|alice@example.com|2000000000\n"
        "100\t0\tfile.py\n"
        "h2|Bob|bob@example.com|1000000000\n"
        "1\t0\tfile.py\n"
    )
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: fake_log)
    report = compute_ownership(
        "/repo", "/repo/file.py", top_n=2, use_complexity_delta=False
    )
    assert report.total_commits == 2
    names = [c.name for c in report.top_contributors]
    # 더 많이 변경 + 더 최근인 Alice가 상위
    assert names[0] == "Alice"


def test_changed_line_ranges_parses_hunks(monkeypatch):
    diff = (
        "@@ -1,2 +1,3 @@\n"      # 추가 → (1,3)
        " ctx\n+new\n"
        "@@ -10 +12,0 @@\n"      # 순수 삭제 → (12,12)
        "-gone\n"
        "@@ -5,0 +6 @@\n"        # count 생략 → 1 → (6,6)
        "+added\n"
    )
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: diff)
    assert _changed_line_ranges("/r", "h", "file.py") == [(1, 3), (12, 12), (6, 6)]


def test_changed_line_ranges_none_on_diff_failure(monkeypatch):
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: None)
    assert _changed_line_ranges("/r", "h", "file.py") is None


def test_touched_max_ccn_credits_only_touched_function(monkeypatch):
    """건드린 함수만 가중 — 복잡한 함수 vs 단순 함수 라인을 분리해 확인."""
    diffs = {
        "hHairy": "@@ -5,1 +5,3 @@\n+    pass\n",     # hairy() 본문(라인5-7)
        "hSimple": "@@ -2,1 +2,1 @@\n+    return 1\n",  # simple() 본문(라인2)
        "hOutside": "@@ -3,0 +3 @@\n+import os\n",      # 함수 밖(라인3)
    }
    monkeypatch.setattr(ownership, "_run_git", _git_with_diffs("", diffs))
    assert _touched_max_ccn("/r", "hHairy", "file.py") == 4
    assert _touched_max_ccn("/r", "hSimple", "file.py") == 1
    assert _touched_max_ccn("/r", "hOutside", "file.py") == 0  # 함수 안 건드림


def test_touched_max_ccn_none_on_diff_failure(monkeypatch):
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: None)
    assert _touched_max_ccn("/r", "h", "file.py") is None


def test_compute_ownership_function_level_attribution(monkeypatch):
    """복잡한 함수를 만진 Alice가, 단순 함수를 만진 Bob보다 높게 매칭된다.

    옛 파일 단위 max CCN이면 둘 다 같은 파일 max(4)로 가중돼 차이가 안 났다.
    함수 단위 매칭에선 실제 만진 함수 복잡도로 갈린다.
    """
    log = (
        "hAlice|Alice|alice@example.com|1500000000\n"
        "3\t0\tfile.py\n"
        "hBob|Bob|bob@example.com|1500000000\n"  # 같은 시각 → 최근성 동일
        "3\t0\tfile.py\n"
    )
    diffs = {
        "hAlice": "@@ -5,1 +5,3 @@\n+    pass\n",       # hairy()
        "hBob": "@@ -2,1 +2,1 @@\n+    return 1\n",       # simple()
    }
    monkeypatch.setattr(ownership, "_run_git", _git_with_diffs(log, diffs))
    report = compute_ownership(
        "/repo", "/repo/file.py", top_n=2, use_complexity_delta=True
    )
    names = [c.name for c in report.top_contributors]
    assert names[0] == "Alice"  # 복잡한 함수를 만진 사람이 상위
    scores = {c.name: c.score for c in report.top_contributors}
    assert scores["Alice"] > scores["Bob"]


def test_compute_ownership_merges_same_email(monkeypatch):
    # 같은 이메일, 다른 표시 이름(mailmap 적용 전 흔한 상황)은 한 사람으로 합산된다.
    # 표시 이름은 가장 최근 커밋(Alice Kim) 기준.
    fake_log = (
        "h1|Alice Kim|alice@example.com|2000000000\n"
        "5\t0\tfile.py\n"
        "h2|alicek|alice@example.com|1000000000\n"
        "5\t0\tfile.py\n"
    )
    monkeypatch.setattr(ownership, "_run_git", lambda repo, args: fake_log)
    report = compute_ownership(
        "/repo", "/repo/file.py", top_n=5, use_complexity_delta=False
    )
    assert len(report.top_contributors) == 1  # 두 이름이 한 사람으로 합쳐짐
    top = report.top_contributors[0]
    assert top.name == "Alice Kim"  # 최신 커밋의 표시 이름
    assert top.commit_count == 2
